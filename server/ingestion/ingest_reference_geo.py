#!/usr/bin/env python3
"""
ingest_reference_geo.py — reference / environmental geography adapters for PR.

Wires three catalogued-but-previously-unsourced reference layers from public
federal sources into servable GeoJSON + provenance manifests, following the
``ingest_tiger_pr.py`` pattern (download → cache → WGS84 → ``data/<layer>.geojson``
+ ``data/reference_geo/<layer>_manifest.json``).

  nid   → ``nid_dams``                   National Inventory of Dams
          https://nid.sec.usace.army.mil/api/nation/csv  (national CSV, filter State=PR)
  gnis  → ``gazetteer_pr_domestic_names``  USGS GNIS Domestic Names
          National Map S3 staged product DomesticNames_PR_Text.zip (pipe-delimited)
  nwi   → ``wetlands_nwi_prvi``          USFWS National Wetlands Inventory
          ArcGIS MapServer, tiled + paginated queries over the PR bbox

These are static reference geographies (dam inventory, place-name gazetteer,
wetland footprints), distinct from the operational water/power/outage *records*
owned by aguayluz-pr — in scope for spiderweb's spatial/reference role.

Raw downloads cache under ``--cache-dir`` (git-ignored); only manifests and the
regenerable promoted GeoJSON are handled per docs/DATA_POLICY.md. Uses stdlib
only (urllib/csv/zipfile); no geo extra required.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger("ingest_reference_geo")

USER_AGENT = "spiderweb-pr-reference-geo/1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]

# Puerto Rico bounding box in WGS84: (lon_min, lon_max, lat_min, lat_max).
PR_BBOX = (-68.0, -65.0, 17.0, 19.0)
STATE_FIPS_PR = "72"

NID_CSV_URL = "https://nid.sec.usace.army.mil/api/nation/csv"
GNIS_PR_ZIP_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/"
    "DomesticNames/DomesticNames_PR_Text.zip"
)
NWI_QUERY_URL = (
    "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/"
    "rest/services/Wetlands/MapServer/0/query"
)
NWI_MAX_RECORDS = 1000  # service maxRecordCount


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _in_pr(lat: float, lon: float) -> bool:
    lon_min, lon_max, lat_min, lat_max = PR_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _round_geometry(geom: Any, ndigits: int = 5) -> Any:
    """Recursively round coordinate floats to trim GeoJSON size (~1 m at 5 dp)."""
    if isinstance(geom, float):
        return round(geom, ndigits)
    if isinstance(geom, list):
        return [_round_geometry(g, ndigits) for g in geom]
    if isinstance(geom, dict):
        return {k: _round_geometry(v, ndigits) for k, v in geom.items()}
    return geom


def _get(url: str, timeout: int) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - controlled public gov URLs
        return resp.read()


def _download(url: str, dest: Path, timeout: int, retries: int = 3) -> tuple[int, str]:
    if dest.exists() and dest.stat().st_size > 0:
        log.info("using cached %s (%d bytes)", dest.name, dest.stat().st_size)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                log.info("downloading %s (attempt %d/%d)", url, attempt, retries)
                data = _get(url, timeout)
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(data)
                tmp.replace(dest)
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                last_exc = exc
                log.warning("download attempt %d failed: %s", attempt, exc)
        else:
            raise RuntimeError(f"failed to download {url} after {retries} attempts") from last_exc
    return dest.stat().st_size, _sha256_file(dest)


def _point_feature(lon: float, lat: float, props: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in props.items() if v not in ("", None)}
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": clean,
    }


# ── NID: National Inventory of Dams ──────────────────────────────────────────

def fetch_nid(cache_dir: Path, timeout: int) -> tuple[list[dict], dict]:
    zip_path = cache_dir / "nid_nation.csv"
    src_bytes, src_sha = _download(NID_CSV_URL, zip_path, timeout)
    text = zip_path.read_text(encoding="utf-8", errors="replace").splitlines()
    # First line is a "Data Last Updated:,<date>" banner; the real header follows.
    if text and text[0].lower().startswith("data last updated"):
        text = text[1:]
    reader = csv.DictReader(text)
    feats: list[dict] = []
    skipped = 0
    for row in reader:
        state = (row.get("State") or "").strip()
        if state not in {"PR", "Puerto Rico"}:
            continue
        try:
            lat, lon = float(row["Latitude"]), float(row["Longitude"])
        except (TypeError, ValueError, KeyError):
            skipped += 1
            continue
        if not _in_pr(lat, lon):
            skipped += 1
            continue
        feats.append(_point_feature(lon, lat, {
            "nid_id": row.get("NID ID"),
            "name": row.get("Dam Name"),
            "primary_purpose": row.get("Primary Purpose"),
            "hazard_potential": row.get("Hazard Potential Classification"),
            "year_completed": row.get("Year Completed"),
            "primary_owner_type": row.get("Primary Owner Type"),
        }))
    meta = {"url": NID_CSV_URL, "filename": zip_path.name, "sha256": src_sha,
            "bytes": src_bytes, "skipped": skipped}
    return feats, meta


# ── GNIS: USGS Domestic Names gazetteer ──────────────────────────────────────

def fetch_gnis(cache_dir: Path, timeout: int) -> tuple[list[dict], dict]:
    zip_path = cache_dir / "DomesticNames_PR_Text.zip"
    src_bytes, src_sha = _download(GNIS_PR_ZIP_URL, zip_path, timeout)
    with zipfile.ZipFile(zip_path) as zf:
        txt_name = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        raw = zf.read(txt_name).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="|")
    feats: list[dict] = []
    skipped = 0
    for row in reader:
        # The per-state file cross-lists a few multi-state ocean features; keep
        # only true PR rows (state_numeric == 72).
        if (row.get("state_numeric") or "").strip() != STATE_FIPS_PR:
            continue
        try:
            lat, lon = float(row["prim_lat_dec"]), float(row["prim_long_dec"])
        except (TypeError, ValueError, KeyError):
            skipped += 1
            continue
        if (lat == 0.0 and lon == 0.0) or not _in_pr(lat, lon):
            skipped += 1
            continue
        feats.append(_point_feature(lon, lat, {
            "feature_id": row.get("feature_id"),
            "name": row.get("feature_name"),
            "feature_class": row.get("feature_class"),
            "county_name": row.get("county_name"),
        }))
    meta = {"url": GNIS_PR_ZIP_URL, "filename": zip_path.name, "sha256": src_sha,
            "bytes": src_bytes, "skipped": skipped}
    return feats, meta


# ── NWI: USFWS National Wetlands Inventory ───────────────────────────────────

def _nwi_query(bbox: tuple[float, float, float, float], offset: int, timeout: int) -> list[dict]:
    lon_min, lon_max, lat_min, lat_max = bbox
    params = {
        "where": "1=1",
        "geometry": f"{lon_min},{lat_min},{lon_max},{lat_max}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "Wetlands.OBJECTID,Wetlands.ATTRIBUTE,Wetlands.WETLAND_TYPE,Wetlands.ACRES",
        "returnGeometry": "true",
        "outSR": "4326",
        "orderByFields": "Wetlands.OBJECTID",
        "resultOffset": str(offset),
        "resultRecordCount": str(NWI_MAX_RECORDS),
        "f": "geojson",
    }
    data = _get(f"{NWI_QUERY_URL}?{urlencode(params)}", timeout)
    try:
        return json.loads(data).get("features", [])
    except json.JSONDecodeError:
        return []


def fetch_nwi(cache_dir: Path, timeout: int, tile_deg: float = 0.25,
              bbox: tuple[float, float, float, float] = PR_BBOX) -> tuple[list[dict], dict]:
    """Tiled + paginated fetch. The service is slow on the full-PR envelope, so
    the bbox is split into ``tile_deg`` cells; each tile paginates to exhaustion
    and features are de-duplicated across tile boundaries by OBJECTID."""
    lon_min, lon_max, lat_min, lat_max = bbox
    seen: set[Any] = set()
    feats: list[dict] = []
    tiles = 0
    lat = lat_min
    while lat < lat_max:
        lon = lon_min
        while lon < lon_max:
            cell = (lon, min(lon + tile_deg, lon_max), lat, min(lat + tile_deg, lat_max))
            tiles += 1
            offset = 0
            while True:
                page = _nwi_query(cell, offset, timeout)
                if not page:
                    break
                for f in page:
                    oid = (f.get("properties") or {}).get("Wetlands.OBJECTID")
                    if oid in seen:
                        continue
                    seen.add(oid)
                    props = f.get("properties") or {}
                    feats.append({
                        "type": "Feature",
                        "geometry": _round_geometry(f.get("geometry"), 5),
                        "properties": {
                            "objectid": oid,
                            "attribute": props.get("Wetlands.ATTRIBUTE"),
                            "wetland_type": props.get("Wetlands.WETLAND_TYPE"),
                            "acres": props.get("Wetlands.ACRES"),
                        },
                    })
                if len(page) < NWI_MAX_RECORDS:
                    break
                offset += NWI_MAX_RECORDS
            lon += tile_deg
        lat += tile_deg
    meta = {"url": NWI_QUERY_URL, "filename": None, "sha256": None, "bytes": None,
            "tiles_queried": tiles, "tile_deg": tile_deg}
    return feats, meta


SOURCES: dict[str, dict[str, Any]] = {
    "nid": {"layer": "nid_dams", "geometry": "point", "fetch": fetch_nid},
    "gnis": {"layer": "gazetteer_pr_domestic_names", "geometry": "point", "fetch": fetch_gnis},
    "nwi": {"layer": "wetlands_nwi_prvi", "geometry": "polygon", "fetch": fetch_nwi},
}


def _write_layer(layer: str, feats: list[dict], data_dir: Path, dry_run: bool) -> tuple[bytes, str]:
    fc = {"type": "FeatureCollection", "features": feats}
    payload = json.dumps(fc, ensure_ascii=False).encode("utf-8")
    if not dry_run:
        out = data_dir / f"{layer}.geojson"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(payload)
    return payload, _sha256_bytes(payload)


def run(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir)
    data_dir = Path(args.data_dir)
    which = list(SOURCES) if args.source == "all" else [args.source]

    summary: dict[str, Any] = {"dry_run": bool(args.dry_run), "layers": {}}
    manifest_layers = []
    for key in which:
        spec = SOURCES[key]
        layer = spec["layer"]
        log.info("fetching %s → %s", key, layer)
        feats, src_meta = spec["fetch"](cache_dir, args.timeout)
        payload, out_sha = _write_layer(layer, feats, data_dir, args.dry_run)
        summary["layers"][layer] = {"features": len(feats), "bytes": len(payload)}
        manifest_layers.append({
            "layer": layer,
            "source": src_meta,
            "output": {
                "path": str(data_dir / f"{layer}.geojson"),
                "sha256": out_sha,
                "bytes": len(payload),
                "feature_count": len(feats),
                "geometry_type": spec["geometry"],
            },
        })
        log.info("built %s: %d features, %d bytes", layer, len(feats), len(payload))

    if not args.dry_run:
        man_dir = data_dir / "reference_geo"
        man_dir.mkdir(parents=True, exist_ok=True)
        for entry in manifest_layers:
            manifest = {
                "ingestor": "ingest_reference_geo.py",
                "generated_utc": _utc_now(),
                "layer": entry["layer"],
                "source": entry["source"],
                "output": entry["output"],
            }
            (man_dir / f"{entry['layer']}_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest PR reference/environmental geographies")
    parser.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--cache-dir", default=str(REPO_ROOT / "data" / "reference_geo" / "cache"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and build but write no GeoJSON/manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
