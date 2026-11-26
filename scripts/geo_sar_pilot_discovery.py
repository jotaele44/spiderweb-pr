#!/usr/bin/env python3
"""Bounded, metadata-only discovery for the FED-GEO-SAR-001 pilot extent.

For one bounding box this asks the USGS National Map catalogue which 1 m
elevation files exist, then reads the first bytes of each file to learn its
coordinate system and footprint from the file itself.  No file is downloaded.
Every response is kept byte-for-byte, and the asset ledger is rebuilt from the
kept bytes, so ``replay`` reproduces it offline and refuses if a byte changed.

    # live: needs an explicit grant, "<max_requests>:<granted_by>"
    python scripts/geo_sar_pilot_discovery.py run --grant 150:owner

    # offline: rebuild from kept bytes and compare with the committed ledger
    python scripts/geo_sar_pilot_discovery.py replay

Controls: https only, two named hosts, redirects refused, a hard request
budget, a byte ceiling per response, and a generic user agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.marine_sources import FrozenHttpResponse, freeze_http_response  # noqa: E402
from tools.source_manifestation_seed import (  # noqa: E402
    HeaderError,
    classify,
    footprint_from_header,
)

SCHEMA_VERSION = "spiderweb.geo_sar.pilot_asset_ledger.v0.1"
RECEIPT_VERSION = "spiderweb.geo_sar.discovery_receipt.v0.1"
PILOT_ID = "GEOSAR-PILOT-001"
PILOT_BBOX_WGS84 = (-66.05, 18.30, -65.95, 18.40)
TNM_PRODUCTS_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"
TNM_DATASET = "Digital Elevation Model (DEM) 1 meter"
ALLOWED_HOSTS = frozenset({"tnmaccess.nationalmap.gov", "prd-tnm.s3.amazonaws.com"})
HEADER_BYTES = 65_536
CATALOG_BYTE_CEILING = 4 * 1024 * 1024
USER_AGENT = "metadata-discovery-client/1.0"
RECORDED_HEADERS = frozenset(
    {"content-type", "content-length", "content-range", "etag", "last-modified", "date"}
)
SEGMENT_LEVEL = "L0"
GRID_CRS = "EPSG:6566"

DEM_CATALOG_PATH = "data_sources/elevation/dem_platform_catalog.yml"
# Dataset identity and survey window as the elevation catalogue records them.
# A test checks these against the catalogue file.
DATASET_CATALOG = {
    "USGS_3DEP_1M_PR_PRVI_2018": (
        "usgs_3dep_1m_pr_prvi_2018",
        ("2018-04-17", "2019-04-19"),
    ),
    "USGS_3DEP_1M_PR_PuertoRicoUSVI_D24": (
        "usgs_3dep_1m_pr_puertoricousvi_d24",
        ("2023-12-27", "2025-03-20"),
    ),
}

DEFAULT_EVIDENCE = REPO_ROOT / "evidence/geo_sar/pilot_001/discovery"
DEFAULT_LEDGER = REPO_ROOT / "registry/geo_sar/pilot_001_asset_ledger.json"

Fetch = Callable[[str, str | None], FrozenHttpResponse]


class DiscoveryRefused(RuntimeError):
    """A request was outside what this run is allowed to do."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise DiscoveryRefused(f"redirect refused: {req.full_url} -> {newurl}")


def parse_grant(raw: str) -> tuple[int, str]:
    limit, _, who = raw.partition(":")
    if not limit.isdigit() or int(limit) < 1 or not who.strip():
        raise DiscoveryRefused(
            "a grant is '<max_requests>:<granted_by>'; nothing is granted by default"
        )
    return int(limit), who.strip()


def check_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise DiscoveryRefused(f"only https is allowed: {url}")
    if parts.hostname not in ALLOWED_HOSTS or parts.port not in (None, 443):
        raise DiscoveryRefused(f"host is not on the allow-list: {url}")
    if parts.username or parts.password:
        raise DiscoveryRefused(f"credentials in a URL are refused: {url}")


def live_fetch(*, max_requests: int, timeout: float = 120.0) -> tuple[Fetch, list[int]]:
    """Return a fetcher bound to a request budget, and its counter."""

    opener = build_opener(_NoRedirect)
    used = [0]

    def fetch(url: str, byte_range: str | None) -> FrozenHttpResponse:
        check_url(url)
        if used[0] >= max_requests:
            raise DiscoveryRefused(f"request budget of {max_requests} is spent")
        used[0] += 1
        headers = {"User-Agent": USER_AGENT}
        ceiling = CATALOG_BYTE_CEILING
        if byte_range is not None:
            headers["Range"] = f"bytes={byte_range}"
            ceiling = HEADER_BYTES
        request = Request(url, headers=headers)
        try:
            with opener.open(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(ceiling + 1)
                status = int(response.status)
                recorded = {
                    str(k).lower(): str(v)
                    for k, v in response.headers.items()
                    if str(k).lower() in RECORDED_HEADERS
                }
        except HTTPError as error:
            body = error.read(ceiling + 1)
            status = int(error.code)
            recorded = {
                str(k).lower(): str(v)
                for k, v in error.headers.items()
                if str(k).lower() in RECORDED_HEADERS
            }
        if len(body) > ceiling:
            raise DiscoveryRefused(f"response exceeded {ceiling} bytes: {url}")
        return FrozenHttpResponse(
            request_url=url,
            status=status,
            retrieved_utc=datetime.now(timezone.utc).isoformat(),
            response_sha256=hashlib.sha256(body).hexdigest(),
            response_size=len(body),
            headers=recorded,
            body=body,
        )

    return fetch, used


def replay_fetch(directory: Path) -> Fetch:
    """Serve kept responses; refuse a changed byte or an unknown request."""

    receipt = json.loads((directory / "discovery_receipt.json").read_text("utf-8"))
    table: dict[tuple[str, str | None], FrozenHttpResponse] = {}
    for entry in receipt["requests"]:
        body = (directory / entry["body_file"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["response_sha256"]:
            raise DiscoveryRefused(f"kept bytes changed: {entry['body_file']}")
        table[(entry["request_url"], entry["byte_range"])] = FrozenHttpResponse(
            request_url=entry["request_url"],
            status=entry["status"],
            retrieved_utc=entry["retrieved_utc"],
            response_sha256=entry["response_sha256"],
            response_size=entry["response_size"],
            headers=entry["headers"],
            body=body,
        )

    def fetch(url: str, byte_range: str | None) -> FrozenHttpResponse:
        try:
            return table[(url, byte_range)]
        except KeyError:
            raise DiscoveryRefused(
                f"no kept response for {url} [{byte_range}]"
            ) from None

    return fetch


# -- geometry --------------------------------------------------------------


def _ring(bounds: Sequence[float]) -> dict[str, Any]:
    xmin, ymin, xmax, ymax = bounds
    return {
        "type": "Polygon",
        "coordinates": [
            [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]
        ],
    }


def _to_grid(bounds: Sequence[float], crs: str):
    """Reproject a native bounding box, edge-densified, into the grid CRS."""

    from rasterio.warp import transform_geom
    from shapely.geometry import box, shape

    dense = box(*bounds).segmentize(max(bounds[2] - bounds[0], 1e-9) / 64)
    return shape(transform_geom(crs, GRID_CRS, dense.__geo_interface__))


def _round(value: float, places: int = 3) -> float:
    return round(float(value), places)


def pilot_segments() -> tuple[Any, list[str]]:
    """The pilot extent in the grid CRS and the segments it has area in."""

    from spiderweb.grid_v2_geometry_bindings import (
        ExactGeometryRecord,
        bind_exact_polygon,
    )

    extent = _to_grid(PILOT_BBOX_WGS84, "EPSG:4326")
    result = bind_exact_polygon(
        ExactGeometryRecord("spiderweb-pr", PILOT_ID, extent, GRID_CRS, "PILOT_EXTENT"),
        level=SEGMENT_LEVEL,
    )
    return extent, [row["Cell_ID"] for row in result.bindings]


# -- build -----------------------------------------------------------------


def discover(
    fetch: Fetch, log: list[dict[str, Any]] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the discovery through ``fetch``; return ``(ledger, request_log)``.

    Pass ``log`` to keep the responses already received if a later step fails.
    """

    from shapely.geometry import box
    from shapely.ops import unary_union

    from spiderweb.geographic_grid_v2 import GRID_ID, GRID_VERSION, parse_cell_id

    log = [] if log is None else log

    def call(url: str, byte_range: str | None, purpose: str) -> FrozenHttpResponse:
        response = fetch(url, byte_range)
        log.append({"purpose": purpose, "byte_range": byte_range, "response": response})
        return response

    query = urllib.parse.urlencode(
        {
            "datasets": TNM_DATASET,
            "bbox": ",".join(str(v) for v in PILOT_BBOX_WGS84),
            "max": 100,
            "outputFormat": "JSON",
        }
    )
    catalog = call(f"{TNM_PRODUCTS_URL}?{query}", None, "catalog")
    if catalog.status != 200:
        raise DiscoveryRefused(f"catalogue answered HTTP {catalog.status}")
    payload = json.loads(catalog.body)
    items = payload.get("items", [])
    total = payload.get("total")
    catalog_closed = isinstance(total, int) and total == len(items)

    extent, segment_ids = pilot_segments()
    assets: list[dict[str, Any]] = []
    grid_footprints: dict[str, Any] = {}

    for item in sorted(items, key=lambda i: str(i.get("downloadURL", ""))):
        url = str(item.get("downloadURL", ""))
        object_id = Path(urllib.parse.urlsplit(url).path).stem
        dataset_id, version, manifestation_class = classify(str(item.get("title", "")))
        bbox = item.get("boundingBox") or {}
        record: dict[str, Any] = {
            "asset_id": f"USGS3DEP:{object_id}",
            "source_id": "USGS_3DEP",
            "dataset_id": dataset_id,
            "dataset_version_id": f"{dataset_id}@{version}",
            "manifestation_class": manifestation_class,
            "native_identity": {
                "original_filename": Path(urllib.parse.urlsplit(url).path).name,
                "provider_asset_id": item.get("sourceId"),
                "provider_tile_id": object_id,
                "source_url": url,
                "catalog_snapshot_sha256": catalog.response_sha256,
            },
            "source_provided": {
                "title": item.get("title"),
                "bounding_box_wgs84": [
                    bbox.get("minX"),
                    bbox.get("minY"),
                    bbox.get("maxX"),
                    bbox.get("maxY"),
                ],
                "size_bytes": item.get("sizeInBytes"),
                "publication_date": item.get("publicationDate"),
                "last_updated": item.get("lastUpdated"),
                "date_created": item.get("dateCreated"),
                "format": item.get("format"),
                "metadata_url": item.get("metaUrl"),
            },
            "verified": {
                "verification_status": "UNVERIFIED",
                "method": None,
            },
            "integrity": {
                "expected_size_bytes": item.get("sizeInBytes"),
                "expected_checksum": None,
                "computed_sha256": None,
                "verification_status": "NOT_ACQUIRED",
            },
            "availability": {
                "discovery_status": "DISCOVERED",
                "acquisition_status": "NOT_ACQUIRED",
                "licensing_status": "UNVERIFIED",
                "access_restrictions": None,
            },
            "storage": {"artifact_id": None, "local_path": None},
            "discrepancies": [],
        }
        try:
            check_url(url)
            head = call(url, f"0-{HEADER_BYTES - 1}", f"header:{object_id}")
            if head.status not in (200, 206):
                raise HeaderError(f"HTTP {head.status}")
            footprint = footprint_from_header(head.body, label=object_id)
        except (HeaderError, DiscoveryRefused, ValueError, KeyError) as error:
            if isinstance(error, DiscoveryRefused) and "budget" in str(error):
                raise
            record["verified"]["failure"] = f"{type(error).__name__}: {error}"
            assets.append(record)
            continue

        crs = f"EPSG:{footprint.epsg}"
        content_range = head.headers.get("content-range", "")
        object_bytes = (
            int(content_range.rsplit("/", 1)[1])
            if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit()
            else None
        )
        from rasterio.warp import transform_bounds

        wgs = transform_bounds(crs, "EPSG:4326", *footprint.bbox_native, densify_pts=64)
        record["verified"] = {
            "verification_status": "HEADER_VERIFIED",
            "method": f"GeoTIFF tags parsed from the first {head.response_size} bytes",
            "header_sha256": head.response_sha256,
            "native_crs": crs,
            "native_footprint": [_round(v, 6) for v in footprint.bbox_native],
            "footprint_wgs84": [_round(v, 7) for v in wgs],
            "width_px": footprint.width,
            "height_px": footprint.height,
            "native_resolution_m": [footprint.resolution_x, footprint.resolution_y],
            "object_size_bytes": object_bytes,
            "etag": head.headers.get("etag"),
            "last_modified": head.headers.get("last-modified"),
            "horizontal_datum": "UNVERIFIED",
            "vertical_datum": "UNVERIFIED",
            "valid_data_extent": "UNVERIFIED",
        }
        if object_bytes is not None and object_bytes != item.get("sizeInBytes"):
            record["discrepancies"].append(
                {
                    "kind": "SIZE_DISAGREEMENT",
                    "catalog_size_bytes": item.get("sizeInBytes"),
                    "object_size_bytes": object_bytes,
                }
            )
        provided = record["source_provided"]["bounding_box_wgs84"]
        if all(isinstance(v, (int, float)) for v in provided):
            delta = max(abs(a - b) for a, b in zip(provided, wgs))
            record["verified"]["catalog_bbox_max_abs_delta_deg"] = _round(delta, 7)
            if delta > 0.001:
                record["discrepancies"].append(
                    {
                        "kind": "FOOTPRINT_DISAGREEMENT",
                        "max_abs_delta_deg": _round(delta, 7),
                    }
                )
        grid_footprints[record["asset_id"]] = _to_grid(footprint.bbox_native, crs)
        assets.append(record)

    # Reconcile with the registry that existed before this run.
    registry_path = REPO_ROOT / "registry/spatial/source_manifestations.json"
    prior = {
        row["Manifestation_ID"]: row
        for row in json.loads(registry_path.read_text("utf-8"))["manifestations"]
    }
    seen = {a["asset_id"] for a in assets}
    for asset in assets:
        row = prior.get(asset["asset_id"])
        if row is None:
            asset["prior_registration"] = "ABSENT"
            continue
        differences = []
        if row.get("Expected_Bytes") != asset["source_provided"]["size_bytes"]:
            differences.append("Expected_Bytes")
        if row.get("Fetch_Locator") != asset["native_identity"]["source_url"]:
            differences.append("Fetch_Locator")
        native = asset["verified"].get("native_footprint")
        if row.get("Footprint_BBox_Native") and native:
            if (
                max(abs(a - b) for a, b in zip(row["Footprint_BBox_Native"], native))
                > 1e-3
            ):
                differences.append("Footprint_BBox_Native")
            if row.get("Provider_CRS") != asset["verified"]["native_crs"]:
                differences.append("Provider_CRS")
        asset["prior_registration"] = {
            "registry": "registry/spatial/source_manifestations.json",
            "footprint_was": row.get("Footprint_Source"),
            "differences": differences,
        }

    # Reconcile with evidence other lanes already hold for the same files.
    prior_receipt = (
        "evidence/dem_sources/lidar_comparison_2026-11-24/tiles_provenance.json"
    )
    by_url = {
        entry["url"]: (site, entry)
        for site, entries in json.loads(
            (REPO_ROOT / prior_receipt).read_text("utf-8")
        ).items()
        for entry in entries
    }
    for asset in assets:
        catalog_id, window = DATASET_CATALOG[asset["dataset_id"]]
        asset["temporal"] = {
            "observation_start": window[0],
            "observation_end": window[1],
            "publication_date": asset["source_provided"]["publication_date"],
            "source": DEM_CATALOG_PATH,
        }
        asset["dataset_catalog_id"] = catalog_id
        if asset["verified"]["verification_status"] == "HEADER_VERIFIED":
            asset["verified"]["vertical_datum"] = {
                "stated_by_provider": "NAVD88",
                "state": "CONTESTED",
                "registry_conflict": "3dep_vertical_datum_label",
                "source": DEM_CATALOG_PATH,
            }
        found = by_url.get(asset["native_identity"]["source_url"])
        if found is None:
            asset["prior_acquisition"] = None
            continue
        site, entry = found
        tag_now = (asset["verified"].get("etag") or "").strip('"')
        asset["prior_acquisition"] = {
            "receipt": prior_receipt,
            "site": site,
            "acquired_on": "2026-11-24",
            "computed_sha256": entry["sha256"],
            "bytes": entry["bytes"],
            "object_tag_then": entry["etag"],
            "object_tag_now": tag_now or None,
            "object_unchanged_since": bool(tag_now) and tag_now == entry["etag"],
            "size_agrees": entry["bytes"] == asset["source_provided"]["size_bytes"],
            "bytes_held_in_this_checkout": False,
        }

    # Segment requirements: which assets of which version cover each segment.
    versions = sorted({a["dataset_version_id"] for a in assets})
    segments = []
    for cell_id in segment_ids:
        cell = parse_cell_id(cell_id)
        cell_box = box(*cell.bounds)
        in_extent = cell_box.intersection(extent).area / cell_box.area
        by_version: dict[str, Any] = {}
        for version in versions:
            parts, required = [], []
            for asset in assets:
                shape_ = grid_footprints.get(asset["asset_id"])
                if asset["dataset_version_id"] != version or shape_ is None:
                    continue
                overlap = shape_.intersection(cell_box)
                if overlap.area > 1e-6:
                    parts.append(overlap)
                    required.append(
                        {
                            "asset_id": asset["asset_id"],
                            "manifestation_class": asset["manifestation_class"],
                            "segment_fraction": _round(overlap.area / cell_box.area, 6),
                        }
                    )
            covered = unary_union(parts).area / cell_box.area if parts else 0.0
            by_version[version] = {
                "footprint_coverage_fraction": _round(covered, 6),
                "intersecting_assets": sorted(required, key=lambda r: r["asset_id"]),
            }
        segments.append(
            {
                "segment_id": cell_id,
                "bounds_epsg6566": list(cell.bounds),
                "fraction_inside_pilot_extent": _round(in_extent, 6),
                "dataset_versions": by_version,
            }
        )

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": PILOT_ID,
        "pilot_extent": {
            "bbox_wgs84": list(PILOT_BBOX_WGS84),
            "bounds_epsg6566": [_round(v) for v in extent.bounds],
            "area_m2": _round(extent.area, 1),
        },
        "segmentation": {
            "grid_id": GRID_ID,
            "grid_version": GRID_VERSION,
            "level": SEGMENT_LEVEL,
            "segment_count": len(segments),
            "rule": "segments with positive area inside the pilot extent",
        },
        "catalog": {
            "provider": "USGS TNM Access",
            "request_url": catalog.request_url,
            "snapshot_sha256": catalog.response_sha256,
            "reported_total": total,
            "items_returned": len(items),
            "denominator_state": "CLOSED" if catalog_closed else "OPEN",
        },
        "dataset_versions": [
            {
                "dataset_version_id": version,
                "asset_count": sum(a["dataset_version_id"] == version for a in assets),
                "header_verified": sum(
                    a["dataset_version_id"] == version
                    and a["verified"]["verification_status"] == "HEADER_VERIFIED"
                    for a in assets
                ),
                "native_crs": sorted(
                    {
                        a["verified"]["native_crs"]
                        for a in assets
                        if a["dataset_version_id"] == version
                        and "native_crs" in a["verified"]
                    }
                ),
                "total_size_bytes": sum(
                    a["source_provided"]["size_bytes"] or 0
                    for a in assets
                    if a["dataset_version_id"] == version
                ),
            }
            for version in versions
        ],
        "registered_before_but_not_listed_now": sorted(set(prior) - seen),
        "assets": assets,
        "segments": segments,
        "limits": [
            "A footprint is the file's raster extent, not the extent of valid data.",
            "This run downloaded no file: data voids are UNVERIFIED.",
            (
                "A prior_acquisition hash was computed by an earlier run in another lane;"
                + " those bytes are not held here and were not re-verified."
            ),
            "Coverage fractions are footprint coverage of a segment, not data coverage.",
        ],
    }
    return ledger, log


def write_evidence(
    directory: Path, log: list[dict[str, Any]], *, budget: int, granted_by: str
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    requests_out = []
    for index, entry in enumerate(log):
        response: FrozenHttpResponse = entry["response"]
        body_path, _ = freeze_http_response(
            response, directory, stem=f"req_{index:04d}"
        )
        requests_out.append(
            {
                "index": index,
                "purpose": entry["purpose"],
                "byte_range": entry["byte_range"],
                "body_file": body_path.name,
                **response.manifest(),
            }
        )
    receipt = {
        "schema_version": RECEIPT_VERSION,
        "pilot_id": PILOT_ID,
        "authorization": {
            "level": "METADATA_DISCOVERY",
            "granted_by": granted_by,
            "max_requests": budget,
        },
        "requests_made": len(log),
        "allowed_hosts": sorted(ALLOWED_HOSTS),
        "hosts_contacted": sorted(
            {urllib.parse.urlsplit(r["request_url"]).hostname for r in requests_out}
        ),
        "bytes_received": sum(r["response_size"] for r in requests_out),
        "data_products_downloaded": 0,
        "largest_response_bytes": max(r["response_size"] for r in requests_out),
        "requests": requests_out,
    }
    (directory / "discovery_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("run", "replay"))
    parser.add_argument("--grant", default="", help="<max_requests>:<granted_by>")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--write",
        action="store_true",
        help="with replay: rewrite the ledger from the kept bytes",
    )
    args = parser.parse_args(argv)

    try:
        if args.mode == "run":
            budget, who = parse_grant(args.grant)
            if (args.evidence / "discovery_receipt.json").exists():
                raise DiscoveryRefused(
                    f"{args.evidence} already holds a run; kept evidence is not overwritten"
                )
            fetch, used = live_fetch(max_requests=budget)
            log: list[dict[str, Any]] = []
            try:
                ledger, _ = discover(fetch, log)
            finally:
                # Requests already spent are evidence whether or not the build
                # succeeded; ``replay`` can finish the work offline.
                if log:
                    write_evidence(args.evidence, log, budget=budget, granted_by=who)
            args.ledger.parent.mkdir(parents=True, exist_ok=True)
            args.ledger.write_text(_dump(ledger), encoding="utf-8")
            print(
                f"requests made: {used[0]} of {budget}; assets: {len(ledger['assets'])}"
            )
            return 0
        ledger, _ = discover(replay_fetch(args.evidence))
        rebuilt = _dump(ledger)
        if args.write:
            args.ledger.write_text(rebuilt, encoding="utf-8")
            print(f"rewrote {args.ledger.name} from kept bytes; no request was made")
            return 0
        if not args.ledger.exists():
            print(f"no ledger at {args.ledger}", file=sys.stderr)
            return 1
        if args.ledger.read_text("utf-8") != rebuilt:
            print("replay does not reproduce the committed ledger", file=sys.stderr)
            return 1
        print(f"replay reproduces {args.ledger.name}: {len(ledger['assets'])} assets")
        return 0
    except DiscoveryRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
