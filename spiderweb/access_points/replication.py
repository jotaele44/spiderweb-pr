"""A declared search for an independent second survey of seabed depressions.

A depression seen in one survey is replicated only by a *different*
acquisition: another cruise, another year, other soundings.  A finer reading
of the same file, or another product made from the same cruise, is not
replication.  This module records, reproducibly, what such a search found:

* which multibeam cruises' footprint polygons contain each depression's
  deepest point, from one frozen answer of the NCEI footprint service;
* which of those cruises are probably the same acquisition as the survey the
  depressions came from (same platform, same year, a shared instrument model),
  read from the cruises' own attributes and the survey's frozen landing page;
* which file categories NCEI holds for each cruise, from the frozen discovery
  catalogue: raw pings only, or processed (gridded) products too;
* for a gridded candidate product that was fetched, where its data actually
  lie, read once from the held file (a footprint or catalogue box is not
  coverage);
* for a gridded product examined earlier, what its committed receipt says
  about the depths it reaches.

The report is sealed and is rebuilt from committed evidence alone, except the
candidate product's facts, which are read from the held file at extract time
and committed with its hash.  Nothing here downloads anything, attaches
anything to a record, or turns a footprint into a measurement.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml

from federation.spatial_core import canonical_json_sha256

from . import CONTRACT_VERSION, survey
from .acquisition import replay_transport
from .bathymetry_run import REPORT_NAME as SEABED_REPORT_NAME
from .bathymetry_run import REPORT_SCHEMA as SEABED_REPORT_SCHEMA
from .namespaces import Namespace
from .products import MANIFEST_SCHEMA, ProductRequest, held_product
from .survey_run import RUNS_VERSION, SURVEY_DIR

SEARCHES_KEY = "replication_searches"
REPORT_FILE = "replication_search.json"
REPORT_SCHEMA = "access_point_replication_search/1.0"
FACTS_FILE = "candidate_product_facts.json"
FACTS_SCHEMA = "access_point_replication_candidate_facts/1.0"
DISCOVERY_CATALOGUE = (
    "evidence/access_points/source_discovery/2026-11-16/source_catalogue.json"
)
_HEX = set("0123456789abcdef")


class ReplicationSearchError(ValueError):
    """The search declaration or its committed evidence is not usable."""


# -- declaration -----------------------------------------------------------


def load_search(config_path: str | Path, search_id: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("version") != RUNS_VERSION:
        raise ReplicationSearchError(f"{config_path}: unsupported survey-run file")
    for entry in data.get(SEARCHES_KEY) or []:
        if str(entry.get("search_id")) == search_id:
            return _validated(dict(entry))
    raise ReplicationSearchError(f"no replication search {search_id!r} is declared")


def _validated(entry: dict[str, Any]) -> dict[str, Any]:
    forbidden = sorted(
        set(entry) & {"center", "centre", "lon", "lat", "points", "coordinates", "bbox"}
    )
    if forbidden:
        raise ReplicationSearchError(
            f"a search may not state positions ({forbidden}); they are read from "
            "the earlier run's report"
        )
    try:
        namespace = Namespace(entry.get("registry"))
    except ValueError as exc:
        raise ReplicationSearchError("a search must name a registry") from exc
    if namespace is not Namespace.ACCESS_POINT_OFFSHORE:
        raise ReplicationSearchError("a seabed replication search is off-shore")
    for key in (
        "earlier_run",
        "reference_run",
        "reference_landing_page",
        "footprint_query",
        "discovery_target",
    ):
        if not str(entry.get(key) or "").strip():
            raise ReplicationSearchError(f"{key} is required")
    candidate = entry.get("candidate_product")
    if candidate is not None:
        candidate = dict(candidate)
        for key in ("filename", "native_identifier", "url", "landing_page"):
            if not str(candidate.get(key) or "").strip():
                raise ReplicationSearchError(f"candidate_product: {key} is required")
        digest = str(candidate.get("sha256") or "")
        if len(digest) != 64 or not set(digest) <= _HEX:
            raise ReplicationSearchError("candidate_product: sha256 must be 64 hex")
        entry["candidate_product"] = candidate
    return entry


def _dir(repo_root: Path, search: Mapping[str, Any]) -> Path:
    return repo_root / SURVEY_DIR / str(search["search_id"])


def _sealed(path: Path, schema: str) -> dict[str, Any]:
    if not path.is_file():
        raise ReplicationSearchError(f"{path.name} is missing")
    document = json.loads(path.read_text(encoding="utf-8"))
    body = dict(document)
    stated = body.pop("content_sha256", None)
    if document.get("schema") != schema or canonical_json_sha256(body) != stated:
        raise ReplicationSearchError(f"{path.name} does not match its content hash")
    return document


def _write_json(path: Path, document: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- pure parts ------------------------------------------------------------


def _ring_contains(ring: list[list[float]], x: float, y: float) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def polygon_contains(rings: list[list[list[float]]], x: float, y: float) -> bool:
    """Esri polygon rings by the even-odd rule: holes and parts both handled."""

    return sum(_ring_contains(r, x, y) for r in rings if len(r) >= 3) % 2 == 1


def footprint_cover(
    payload: Mapping[str, Any], points: Mapping[str, tuple[float, float]]
) -> dict[str, dict[str, Any]]:
    """For each cruise in a footprint answer, which named points it contains."""

    if "error" in payload or not isinstance(payload.get("features"), list):
        raise ReplicationSearchError("the footprint answer is not a feature list")
    cruises: dict[str, dict[str, Any]] = {}
    for feature in payload["features"]:
        attrs = feature.get("attributes") or {}
        survey_id = str(attrs.get("SURVEY_ID") or "").strip()
        if not survey_id:
            raise ReplicationSearchError("a footprint feature names no survey")
        rings = (feature.get("geometry") or {}).get("rings") or []
        row = cruises.setdefault(
            survey_id,
            {
                "survey_id": survey_id,
                "platform": attrs.get("PLATFORM"),
                "instrument": attrs.get("INSTRUMENT"),
                "survey_year": attrs.get("SURVEY_YEAR"),
                "source": attrs.get("SOURCE"),
                "footprint_features": 0,
                "contains": [],
            },
        )
        row["footprint_features"] += 1
        for name, (x, y) in points.items():
            if name not in row["contains"] and polygon_contains(rings, x, y):
                row["contains"].append(name)
    for row in cruises.values():
        row["contains"].sort()
    return dict(sorted(cruises.items()))


def _platform_key(text: Any) -> str:
    cleaned = re.sub(r"\(.*?\)", " ", str(text or ""))
    cleaned = re.sub(r"\b(noaa|ship|r/v|rv|usns)\b", " ", cleaned, flags=re.I)
    return " ".join(cleaned.upper().split())


def _models(text: Any) -> set[str]:
    return set(re.findall(r"\b\d{3,4}\b", str(text or "")))


def landing_page_facts(body: bytes) -> dict[str, Any]:
    """Vessel, dates and instrument models a NOS survey landing page states."""

    text = html.unescape(
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8")))
    )
    start = re.search(r"Start Date:\s*(\d{4}-\d{2}-\d{2})", text)
    end = re.search(r"End Date:\s*(\d{4}-\d{2}-\d{2})", text)
    vessel = re.search(
        r"Chief\(s\) of Party\s+(NOAA Ship [A-Z .]+?)\s+[A-Z][a-z]", text
    )
    instruments = re.search(r"Instrument Type\s+(.*?)\s+Source Data", text)
    return {
        "start_date": start.group(1) if start else None,
        "end_date": end.group(1) if end else None,
        "vessel": vessel.group(1).strip() if vessel else None,
        "instruments": instruments.group(1).strip() if instruments else None,
    }


def independence(
    cruise: Mapping[str, Any], reference: Mapping[str, Any]
) -> dict[str, Any]:
    """Is a cruise probably the same acquisition as the reference survey?

    Same platform, same year and at least one shared instrument model number:
    PROBABLY_THE_SAME_SOUNDINGS.  Otherwise INDEPENDENT_ACQUISITION.  Either
    way it is an inference from catalogue attributes, never a proof.
    """

    year = str(reference.get("start_date") or "")[:4]
    ref_platform = _platform_key(reference.get("vessel"))
    cruise_platform = _platform_key(cruise.get("platform"))
    same_platform = bool(
        ref_platform and cruise_platform and ref_platform in cruise_platform
    )
    same_year = bool(year) and str(cruise.get("survey_year")) == year
    shared = sorted(
        _models(cruise.get("instrument")) & _models(reference.get("instruments"))
    )
    same = same_platform and same_year and bool(shared)
    return {
        "same_platform": same_platform,
        "same_year": same_year,
        "shared_instrument_models": shared,
        "relation": (
            "PROBABLY_THE_SAME_SOUNDINGS" if same else "INDEPENDENT_ACQUISITION"
        ),
        "basis": "INFERENCE from catalogue attributes and the survey's landing page",
    }


def file_categories(
    catalogue: Mapping[str, Any], target: str
) -> dict[str, list[dict[str, Any]]]:
    """NCEI file categories per multibeam cruise, as the discovery run listed them."""

    out: dict[str, list[dict[str, Any]]] = {}
    for source in catalogue.get("sources") or []:
        if source.get("family") != "MULTIBEAM_SURVEY_CATALOG":
            continue
        scoped = (source.get("query_scoped_attributes") or {}).get(
            "fileStatsByCat"
        ) or {}
        stats = scoped.get(target)
        if stats is None:
            continue
        survey_id = str(source["native_identifier"]).split(":")[-1]
        out[survey_id] = sorted(
            (
                {"category": s["name"], "files": s["count"], "bytes": s["size"]}
                for s in stats
            ),
            key=lambda r: r["category"],
        )
    return out


# -- the earlier run's depressions -----------------------------------------


def _sealed_seabed_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReplicationSearchError(f"{path} is missing")
    report = json.loads(path.read_text(encoding="utf-8"))
    body = dict(report)
    stated = body.pop("content_sha256", None)
    if (
        report.get("schema") != SEABED_REPORT_SCHEMA
        or canonical_json_sha256(body) != stated
    ):
        raise ReplicationSearchError(f"{path} does not match its content hash")
    return report


def _points(
    repo_root: Path, search: Mapping[str, Any]
) -> tuple[
    dict[str, Any], dict[str, tuple[float, float]], dict[str, tuple[float, float]]
]:
    """The earlier run's outer depressions: deepest points in lon/lat and in its CRS."""

    path = repo_root / SURVEY_DIR / str(search["earlier_run"]) / SEABED_REPORT_NAME
    report = _sealed_seabed_report(path)
    rows = [
        row
        for row in report["products"][0]["result"]["detections"]
        if row.get("hierarchy_level", 0) == 0
    ]
    crs = report["products"][0]["result"]["surface"]["crs"]
    xy = {row["native_record_id"]: tuple(row["deepest_xy"]) for row in rows}
    converted = survey._lonlat(
        crs, [v[0] for v in xy.values()], [v[1] for v in xy.values()]
    )
    lonlat = dict(zip(xy, converted))
    return report, lonlat, xy


# -- the candidate product (extract half) ----------------------------------


def candidate_coverage(
    path: str | Path, points_xy: Mapping[str, tuple[float, float]], points_crs: str
) -> dict[str, Any]:
    """Where a held gridded product has data, and how far that is from each point."""

    rasterio = survey._rasterio()
    with rasterio.open(path) as src:
        crs, basis = survey.horizontal_crs_with_basis(src.crs)
        nodata = src.nodatavals[0]
        values = src.read(1).astype(np.float64)
        t = src.transform
        shape = (src.height, src.width)
    if crs != points_crs:
        raise ReplicationSearchError(
            f"the candidate is on {crs}, the points on {points_crs}; not compared"
        )
    covered = np.isfinite(values) & (values != nodata)
    rows, cols = np.nonzero(covered)
    xs = t.c + (cols + 0.5) * t.a
    ys = t.f + (rows + 0.5) * t.e
    nearest = {}
    for name, (x, y) in points_xy.items():
        d = float(np.hypot(xs - x, ys - y).min()) if xs.size else math.inf
        nearest[name] = round(d, 1)
    cell = float(t.a)
    box = None
    if xs.size:
        corners = survey._lonlat(
            crs, [float(xs.min()), float(xs.max())], [float(ys.min()), float(ys.max())]
        )
        box = [corners[0][0], corners[0][1], corners[1][0], corners[1][1]]
    return {
        "horizontal_crs": crs,
        "horizontal_crs_basis": basis,
        "base_grid_shape": list(shape),
        "base_cell_m": round(cell, 6),
        "covered_base_cells": int(rows.size),
        "covered_cell_centres_lonlat_bbox": box,
        "nearest_covered_cell_centre_m": dict(sorted(nearest.items())),
        "points_within_one_base_cell": sorted(
            name for name, d in nearest.items() if d <= cell
        ),
    }


def _candidate_request(candidate: Mapping[str, Any]) -> ProductRequest:
    return ProductRequest(
        provider="NOS_BAG_PRODUCT",
        native_identifier=candidate["native_identifier"],
        title=candidate["filename"],
        url=candidate["url"],
        metadata_uri=candidate["landing_page"],
    )


def extract(
    search: Mapping[str, Any], *, repo_root: str | Path, product_dir: str | Path
) -> dict[str, Any]:
    """Read the held candidate product once and commit what it shows.  No network."""

    root = Path(repo_root)
    candidate = search.get("candidate_product")
    if candidate is None:
        raise ReplicationSearchError("this search declares no candidate product")
    held = held_product(_candidate_request(candidate), product_dir)
    if held is None:
        raise ReplicationSearchError(
            f"{candidate['filename']} is not held in {product_dir}"
        )
    if held.sha256 != candidate["sha256"]:
        raise ReplicationSearchError("the held candidate is not the declared file")
    report, _, xy = _points(root, search)
    crs = report["products"][0]["result"]["surface"]["crs"]
    coverage = candidate_coverage(held.path, xy, crs)
    out = _dir(root, search)
    manifest = json.loads(
        (Path(product_dir) / (candidate["filename"] + ".manifest.json")).read_text(
            encoding="utf-8"
        )
    )
    _write_json(out / "products" / (candidate["filename"] + ".manifest.json"), manifest)
    body: dict[str, Any] = {
        "schema": FACTS_SCHEMA,
        "search_id": search["search_id"],
        "parent_sha256": held.sha256,
        "earlier_report_content_sha256": report["content_sha256"],
        "read_from": (
            "the held product's base grid; not recomputable from the repository alone"
        ),
        "coverage": coverage,
    }
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    _write_json(out / FACTS_FILE, body)
    return body


# -- the sealed report -----------------------------------------------------


def _prior(
    root: Path, search: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any] | None:
    if not search.get("prior_receipt"):
        return None
    path = root / str(search["prior_receipt"])
    receipt = json.loads(path.read_text(encoding="utf-8"))
    second = receipt.get("second_sensor") or {}
    floors = [
        row["floor_elevation_m"]
        for row in report["products"][0]["result"]["detections"]
        if row.get("hierarchy_level", 0) == 0
    ]
    reaches = second.get("candidate_value_max")
    return {
        "receipt": str(search["prior_receipt"]),
        "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "survey_id": second.get("survey_id"),
        "product": second.get("product"),
        "shallowest_value_on_reference_cells_m": reaches,
        "deepest_depression_floor_m": min(floors) if floors else None,
        "reaches_the_depressions": (
            None if reaches is None or not floors else bool(reaches >= min(floors))
        ),
    }


def _candidate_block(
    root: Path,
    search: Mapping[str, Any],
    report: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> dict[str, Any] | None:
    candidate = search.get("candidate_product")
    if candidate is None:
        return None
    out = _dir(root, search)
    facts = _sealed(out / FACTS_FILE, FACTS_SCHEMA)
    if facts["parent_sha256"] != candidate["sha256"]:
        raise ReplicationSearchError("the candidate facts were read from another file")
    if facts["earlier_report_content_sha256"] != report["content_sha256"]:
        raise ReplicationSearchError(
            "the candidate facts were read against another report"
        )
    manifest_path = out / "products" / (candidate["filename"] + ".manifest.json")
    if not manifest_path.is_file():
        raise ReplicationSearchError("the candidate download manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != MANIFEST_SCHEMA
        or manifest["response_sha256"] != candidate["sha256"]
        or manifest["request"]["url"] != candidate["url"]
    ):
        raise ReplicationSearchError("the candidate download manifest does not match")
    landing = replay_transport(out / "catalogue")(candidate["landing_page"])
    page = landing_page_facts(landing.body)
    if not any(str(asset["url"]) == candidate["url"] for asset in _assets(landing)):
        raise ReplicationSearchError(
            "the candidate is not listed on its frozen landing page"
        )
    coverage = facts["coverage"]
    covers = sorted(coverage["points_within_one_base_cell"])
    return {
        "native_identifier": candidate["native_identifier"],
        "download": {
            "size_bytes": manifest["response_size"],
            "sha256": manifest["response_sha256"],
            "retrieved_utc": manifest["retrieved_utc"],
        },
        "landing_page_facts": page,
        "independence": independence(
            {
                "platform": page.get("vessel"),
                "survey_year": str(page.get("start_date") or "")[:4],
                "instrument": page.get("instruments"),
            },
            reference,
        ),
        "coverage": coverage,
        "coverage_basis": facts["read_from"],
        "covers": covers,
        "outcome": "COVERS_SOME" if covers else "COVERS_NONE_OF_THE_DEPRESSIONS",
    }


def _assets(frozen: Any) -> list[dict[str, Any]]:
    from pipeline.marine_alternate_products import (
        parse_nos_product_links,
    )  # noqa: PLC0415

    return list(parse_nos_product_links(frozen).assets)


def build_report(search: Mapping[str, Any], *, repo_root: str | Path) -> dict[str, Any]:
    """The sealed search report, rebuilt from committed evidence."""

    root = Path(repo_root)
    out = _dir(root, search)
    report, points, xy = _points(root, search)
    footprints = replay_transport(out / "catalogue")(str(search["footprint_query"]))
    payload = json.loads(footprints.body.decode("utf-8"))
    cruises = footprint_cover(payload, points)
    reference_page = replay_transport(
        root / SURVEY_DIR / str(search["reference_run"]) / "catalogue"
    )(str(search["reference_landing_page"]))
    reference = landing_page_facts(reference_page.body)
    categories = file_categories(
        json.loads((root / DISCOVERY_CATALOGUE).read_text(encoding="utf-8")),
        str(search["discovery_target"]),
    )
    prior = _prior(root, search, report)
    candidate = _candidate_block(root, search, report, reference)
    rows = []
    for survey_id, cruise in cruises.items():
        cats = categories.get(survey_id)
        names = {c["category"] for c in cats or []}
        rows.append(
            {
                **cruise,
                "independence": independence(cruise, reference),
                "ncei_file_categories": cats,
                "gridded_product_at_ncei": (
                    None if cats is None else "MB PROCESSED" in names
                ),
            }
        )
    blocked_by_prior = (
        {prior["survey_id"]}
        if prior and prior["reaches_the_depressions"] is False
        else set()
    )
    usable = [
        r["survey_id"]
        for r in rows
        if r["contains"]
        and r["independence"]["relation"] == "INDEPENDENT_ACQUISITION"
        and r["gridded_product_at_ncei"]
        and r["survey_id"] not in blocked_by_prior
    ]
    raw_only = [
        r["survey_id"]
        for r in rows
        if r["contains"]
        and r["independence"]["relation"] == "INDEPENDENT_ACQUISITION"
        and r["gridded_product_at_ncei"] is False
    ]
    if candidate and candidate["covers"]:
        outcome = "CANDIDATE_COVERS_SOME"
    elif usable:
        outcome = "GRIDDED_INDEPENDENT_PRODUCT_AVAILABLE"
    elif raw_only:
        outcome = "BLOCKED_INDEPENDENT_CRUISES_HOLD_RAW_SOUNDINGS_ONLY"
    else:
        outcome = "NO_INDEPENDENT_CRUISE_FOUND"
    body: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "search_id": search["search_id"],
        "registry": Namespace.ACCESS_POINT_OFFSHORE.value,
        "earlier_run": search["earlier_run"],
        "earlier_report_content_sha256": report["content_sha256"],
        "points": {
            name: {"deepest_lonlat": list(points[name]), "deepest_xy": list(xy[name])}
            for name in sorted(points)
        },
        "points_basis": (
            "the deepest point of each outer depression in the earlier run's "
            "report; not typed"
        ),
        "reference_survey": {"run": search["reference_run"], **reference},
        "footprint_answer": {
            "request_url": footprints.request_url,
            "response_sha256": footprints.response_sha256,
            "retrieved_utc": footprints.retrieved_utc,
            "features": len(payload["features"]),
        },
        "cruises": rows,
        "prior_gridded_product": prior,
        "candidate_product": candidate,
        "independent_cruises_with_gridded_product_covering": usable,
        "independent_cruises_with_raw_soundings_only": raw_only,
        "outcome": outcome,
        "registry_changes": 0,
        "limits": [
            "a footprint polygon is where a cruise ran its sonar, generalised; it is not coverage of any one point",
            "a catalogue or survey bounding box is not coverage; the candidate product was checked against its own grid",
            "whether two cruises are the same acquisition is inferred from platform, year and instrument; it is not proven",
            "raw multibeam soundings were not processed: a grid made here from raw pings without the cruise's own corrections would not be evidence",
            "nothing was attached to any record and no depression changed tier",
        ],
    }
    body = json.loads(json.dumps(body))
    body["content_sha256"] = canonical_json_sha256(body)
    return body


def write_report(report: Mapping[str, Any], *, repo_root: str | Path) -> str:
    return _write_json(
        Path(repo_root) / SURVEY_DIR / str(report["search_id"]) / REPORT_FILE, report
    )


def check_report(search: Mapping[str, Any], *, repo_root: str | Path) -> list[str]:
    """Problems found when the committed report is recomputed from evidence."""

    root = Path(repo_root)
    path = _dir(root, search) / REPORT_FILE
    if not path.is_file():
        return ["no report is committed for this search"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    try:
        rebuilt = build_report(search, repo_root=root)
    except (ReplicationSearchError, ValueError, LookupError, OSError) as exc:
        return [f"{type(exc).__name__}: {exc}"]
    if rebuilt == committed:
        return []
    differing = sorted(
        key
        for key in set(rebuilt) | set(committed)
        if rebuilt.get(key) != committed.get(key)
    )
    return [f"the committed report is not reproduced; differing fields: {differing}"]
