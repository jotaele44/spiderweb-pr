#!/usr/bin/env python3
"""
ingest_pr_boundaries.py — Ingest the two sourced entries of the Spatial
Boundary Registry (configs/spatial_boundaries.yaml): PR_CORE_BOUNDARY and
PR_EEZ_LEGAL_BOUNDARY.

Sources:
    PR_CORE_BOUNDARY      ← U.S. Census TIGER/Line STATE national file,
                            filtered to STATEFP=72 (Puerto Rico). Same base
                            URL/vintage pattern as ingest_tiger_pr.py's other
                            layers.
                            https://www2.census.gov/geo/tiger/TIGER<year>/STATE/tl_<year>_us_state.zip

    PR_EEZ_LEGAL_BOUNDARY ← NOAA Office of Coast Survey "200NM EEZ and
                            Maritime Boundaries" layer (MapServer/3), filtered
                            to REGION='Puerto Rico and U.S. Virgin Islands'.
                            Includes the EEZ limit itself (Presidential
                            Proclamation No. 5030, March 1983) plus adjacent
                            bilateral treaty boundary lines. Geometry is
                            polyline (the boundary itself), not a filled
                            polygon — that is the authoritative representation
                            NOAA publishes.
                            https://maritimeboundaries.noaa.gov/arcgis/rest/services/MaritimeBoundaries/US_Maritime_Limits_Boundaries/MapServer/3/query

Output: data/pr_core_boundary.geojson, data/pr_eez_legal_boundary.geojson
(gitignored — regenerable, never committed, per docs/DATA_POLICY.md), plus a
provenance record printed to stdout as JSON so a caller can paste the
source_url/retrieval_date/geometry_hash fields into
configs/spatial_boundaries.yaml by hand. This script does NOT write the YAML
registry itself — boundary status changes are a reviewed, deliberate edit,
not something a re-run should silently flip.

Heavy GIS deps (geopandas/pyogrio) are imported lazily, matching
ingest_tiger_pr.py, so this module imports cleanly without the ``geo`` extra.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("ingest_pr_boundaries")

USER_AGENT = "spiderweb-pr-boundary-ingest/1.0"
TIGER_BASE = "https://www2.census.gov/geo/tiger/TIGER{year}/"
STATE_FIPS_PR = "72"

NOAA_EEZ_QUERY_URL = (
    "https://maritimeboundaries.noaa.gov/arcgis/rest/services/"
    "MaritimeBoundaries/US_Maritime_Limits_Boundaries/MapServer/3/query"
)
NOAA_EEZ_REGION = "Puerto Rico and U.S. Virgin Islands"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, timeout: int, retries: int = 3) -> tuple[int, str]:
    """Download url to dest (cached; reused if already present)."""
    import requests

    if dest.exists() and dest.stat().st_size > 0:
        log.info("using cached %s (%d bytes)", dest.name, dest.stat().st_size)
    else:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                log.info("downloading %s (attempt %d/%d)", url, attempt, retries)
                with requests.get(
                    url,
                    stream=True,
                    timeout=timeout,
                    headers={"User-Agent": USER_AGENT},
                ) as resp:
                    resp.raise_for_status()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with tmp.open("wb") as handle:
                        for chunk in resp.iter_content(chunk_size=1 << 16):
                            if chunk:
                                handle.write(chunk)
                    tmp.replace(dest)
                break
            except Exception as exc:  # noqa: BLE001 - retry any transient network error
                last_exc = exc
                log.warning("download attempt %d failed: %s", attempt, exc)
        else:
            raise RuntimeError(
                f"failed to download {url} after {retries} attempts"
            ) from last_exc

    return dest.stat().st_size, _sha256_file(dest)


def ingest_core_boundary(
    year: int, cache_dir: Path, data_dir: Path, timeout: int, dry_run: bool
) -> dict[str, Any]:
    """PR_CORE_BOUNDARY ← TIGER STATE national file filtered to STATEFP=72."""
    import geopandas as gpd

    base = TIGER_BASE.format(year=year)
    filename = f"tl_{year}_us_state.zip"
    url = f"{base}STATE/{filename}"
    zip_path = cache_dir / filename

    src_bytes, src_sha = _download(url, zip_path, timeout)

    gdf = gpd.read_file(f"zip://{zip_path.resolve()}")
    gdf = gdf[gdf["STATEFP"] == STATE_FIPS_PR].copy()
    if gdf.empty:
        raise RuntimeError(f"no STATEFP={STATE_FIPS_PR} feature found in {url}")
    gdf = gdf[["GEOID", "NAME", "geometry"]].copy()
    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)

    payload = gdf.to_json().encode("utf-8")
    out_path = data_dir / "pr_core_boundary.geojson"
    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)

    return {
        "boundary_id": "PR_CORE_BOUNDARY",
        "source_authority": "U.S. Census Bureau, TIGER/Line",
        "source_url": url,
        "retrieval_date": _utc_now(),
        "edition_date": f"{year}",
        "source_crs": "EPSG:4269 (NAD83, as published)",
        "normalized_crs": "EPSG:4326",
        "geometry_hash": f"sha256:{_sha256_bytes(payload)}",
        "geometry_ref": (
            out_path.relative_to(data_dir.parent).as_posix() if not dry_run else None
        ),
        "feature_count": int(len(gdf)),
        "output_bytes": len(payload),
        "source_zip": {"bytes": src_bytes, "sha256": src_sha},
    }


def ingest_eez_boundary(data_dir: Path, timeout: int, dry_run: bool) -> dict[str, Any]:
    """PR_EEZ_LEGAL_BOUNDARY ← NOAA Office of Coast Survey maritime limits."""
    import requests

    params = {
        "where": f"REGION='{NOAA_EEZ_REGION}'",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
    }
    log.info("querying NOAA maritime boundaries: REGION='%s'", NOAA_EEZ_REGION)
    resp = requests.get(
        NOAA_EEZ_QUERY_URL,
        params=params,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    payload = resp.content
    geojson = json.loads(payload)
    if not geojson.get("features"):
        raise RuntimeError(
            f"NOAA query returned no features for REGION='{NOAA_EEZ_REGION}'"
        )

    out_path = data_dir / "pr_eez_legal_boundary.geojson"
    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)

    return {
        "boundary_id": "PR_EEZ_LEGAL_BOUNDARY",
        "source_authority": (
            "NOAA Office of Coast Survey — U.S. Maritime Limits and Boundaries"
        ),
        "source_url": f"{NOAA_EEZ_QUERY_URL}?{requests.compat.urlencode(params)}",
        "retrieval_date": _utc_now(),
        "edition_date": (
            "2003-12-01 approved / 2006-01-01 published "
            "(per PUB_DATE/APPRV_DATE fields)"
        ),
        "source_crs": "EPSG:4326 (as published)",
        "normalized_crs": "EPSG:4326",
        "geometry_hash": f"sha256:{_sha256_bytes(payload)}",
        "geometry_ref": (
            out_path.relative_to(data_dir.parent).as_posix() if not dry_run else None
        ),
        "feature_count": int(len(geojson["features"])),
        "output_bytes": len(payload),
        "notes": (
            "Includes the 200NM EEZ limit (Presidential Proclamation No. 5030, "
            "March 1983) plus adjacent bilateral treaty boundary lines "
            "(US/UK British Virgin Islands and Anguilla, US/Venezuela). "
            "Geometry is polyline (the boundary itself), matching NOAA's "
            "authoritative representation — not a filled polygon."
        ),
    }


def run(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir)
    data_dir = Path(args.data_dir)

    results = []
    if not args.eez_only:
        results.append(
            ingest_core_boundary(
                args.year, cache_dir, data_dir, args.timeout, args.dry_run
            )
        )
    if not args.core_only:
        results.append(ingest_eez_boundary(data_dir, args.timeout, args.dry_run))

    manifest = {
        "ingestor": "ingest_pr_boundaries.py",
        "generated_utc": _utc_now(),
        "boundaries": results,
    }
    print(json.dumps(manifest, indent=2))
    log.info(
        "Paste the printed source_authority/source_url/retrieval_date/edition_date/"
        "source_crs/normalized_crs/geometry_hash/geometry_ref fields into the matching "
        "entry in configs/spatial_boundaries.yaml and set status: resolved by hand."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest PR_CORE_BOUNDARY (TIGER) and PR_EEZ_LEGAL_BOUNDARY (NOAA)"
    )
    parser.add_argument("--year", type=int, default=2025, help="TIGER vintage year")
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parents[2] / "data"),
        help="Directory for output GeoJSON",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(Path(__file__).resolve().parents[2] / "data" / "tiger" / "cache"),
        help="Directory for cached raw TIGER zip (never committed)",
    )
    parser.add_argument(
        "--timeout", type=int, default=120, help="Per-request timeout (seconds)"
    )
    parser.add_argument(
        "--core-only", action="store_true", help="Only ingest PR_CORE_BOUNDARY"
    )
    parser.add_argument(
        "--eez-only", action="store_true", help="Only ingest PR_EEZ_LEGAL_BOUNDARY"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate but write no GeoJSON output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
