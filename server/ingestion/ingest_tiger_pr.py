#!/usr/bin/env python3
"""
ingest_tiger_pr.py — Ingest U.S. Census TIGER/Line administrative geographies
for Puerto Rico (STATEFP=72) into servable GeoJSON layers + a provenance
manifest, and join site points to their municipio/tract GEOIDs.

Source directory (the vector sibling of the Census map/PDF trees):
    https://www2.census.gov/geo/tiger/TIGER<year>/

Layers produced (written to ``--data-dir``/<layer>.geojson):
    municipios  ← COUNTY   (national county file, filtered to STATEFP=72 → 78)
    tracts      ← TRACT     (tl_<year>_72_tract)
    places      ← PLACE     (tl_<year>_72_place)
    barrios     ← COUSUB    (tl_<year>_72_cousub)
    puma        ← PUMA      (tl_<year>_72_puma20)

Provenance manifest is written to ``--data-dir``/tiger/<year>/manifest.json with
per-layer source (input zip) and output (GeoJSON) SHA256 + byte + feature-count
records. Raw zips are cached under ``--cache-dir`` and never committed (see
docs/DATA_POLICY.md).

Heavy GIS deps (geopandas/pyogrio) are imported lazily so this module imports
cleanly without the ``geo`` extra installed; install it with
``pip install -e ".[geo]"`` to actually run an ingest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # support both `python server/ingestion/ingest_tiger_pr.py` and package import
    from migrations import ensure_sites_geoid_columns
except ImportError:  # pragma: no cover - fallback when cwd differs
    sys.path.insert(0, str(Path(__file__).parent))
    from migrations import ensure_sites_geoid_columns

log = logging.getLogger("ingest_tiger_pr")

USER_AGENT = "spiderweb-pr-tiger-ingest/1.0"
TIGER_BASE = "https://www2.census.gov/geo/tiger/TIGER{year}/"
STATE_FIPS_PR = "72"

# Puerto Rico bounding box in WGS84: (lon_min, lon_max, lat_min, lat_max).
PR_BBOX = (-68.0, -65.0, 17.0, 19.0)

# Upper bound on progressive-simplification passes before a layer is declared
# oversized. Each pass doubles the tolerance.
_MAX_SIMPLIFY_STEPS = 12

# Per-layer ingest specification. Entries are plain dicts (mutable) so tests can
# monkeypatch max_bytes / simplify_tolerance_initial / on_oversize in place.
#   tiger_subdir / tiger_filename → where to fetch the shapefile zip
#   state_filter                  → keep only rows with this STATEFP (county file only)
#   geoid_field / name_field      → source columns normalised to GEOID / NAME
#   max_bytes                     → GeoJSON size budget before simplification
#   simplify_tolerance_initial    → first Douglas-Peucker tolerance (degrees)
#   on_oversize                   → "warn_continue" (flag + keep) or "abort" (raise)
LAYER_SPECS: dict[str, dict[str, Any]] = {
    "municipios": {
        "tiger_subdir": "COUNTY",
        "tiger_filename": "tl_{year}_us_county.zip",
        "state_filter": STATE_FIPS_PR,
        "geoid_field": "GEOID",
        "name_field": "NAMELSAD",
        "max_bytes": 8_000_000,
        "simplify_tolerance_initial": 0.0001,
        "on_oversize": "warn_continue",
    },
    "tracts": {
        "tiger_subdir": "TRACT",
        "tiger_filename": "tl_{year}_72_tract.zip",
        "state_filter": None,
        "geoid_field": "GEOID",
        "name_field": "NAMELSAD",
        "max_bytes": 20_000_000,
        "simplify_tolerance_initial": 0.0001,
        "on_oversize": "warn_continue",
    },
    "places": {
        "tiger_subdir": "PLACE",
        "tiger_filename": "tl_{year}_72_place.zip",
        "state_filter": None,
        "geoid_field": "GEOID",
        "name_field": "NAMELSAD",
        "max_bytes": 12_000_000,
        "simplify_tolerance_initial": 0.0001,
        "on_oversize": "warn_continue",
    },
    "barrios": {
        "tiger_subdir": "COUSUB",
        "tiger_filename": "tl_{year}_72_cousub.zip",
        "state_filter": None,
        "geoid_field": "GEOID",
        "name_field": "NAMELSAD",
        "max_bytes": 20_000_000,
        "simplify_tolerance_initial": 0.0001,
        "on_oversize": "warn_continue",
    },
    "puma": {
        "tiger_subdir": "PUMA20",
        "tiger_filename": "tl_{year}_72_puma20.zip",
        "state_filter": None,
        "geoid_field": "GEOID20",
        "name_field": "NAMELSAD20",
        "max_bytes": 12_000_000,
        "simplify_tolerance_initial": 0.0001,
        "on_oversize": "warn_continue",
    },
}

CORE_LAYERS = ("municipios", "tracts", "places", "barrios")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _isnan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── serialization + size budget ──────────────────────────────────────────────

def _serialize_with_size_check(gdf, layer: str) -> tuple[bytes, float, bool]:
    """Serialize a GeoDataFrame to GeoJSON, simplifying until it fits the budget.

    Returns ``(payload_bytes, tolerance_used, oversized)``. If the payload never
    fits within ``max_bytes`` after ``_MAX_SIMPLIFY_STEPS`` passes, behaviour
    depends on the layer's ``on_oversize``:
      - ``"abort"``          → raise RuntimeError (message contains "GeoJSON still")
      - ``"warn_continue"``  → return the last payload with ``oversized=True``
    """
    spec = LAYER_SPECS[layer]
    max_bytes = int(spec["max_bytes"])

    payload = gdf.to_json().encode("utf-8")
    if len(payload) <= max_bytes:
        return payload, 0.0, False

    tol = float(spec["simplify_tolerance_initial"])
    used_tol = tol
    last = payload
    for _ in range(_MAX_SIMPLIFY_STEPS):
        simplified = gdf.copy()
        simplified["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)
        last = simplified.to_json().encode("utf-8")
        used_tol = tol
        if len(last) <= max_bytes:
            return last, used_tol, False
        tol *= 2

    if spec.get("on_oversize") == "abort":
        raise RuntimeError(
            f"GeoJSON still exceeds {max_bytes} bytes for layer '{layer}' after "
            f"{_MAX_SIMPLIFY_STEPS} simplification passes "
            f"(final size {len(last)} bytes at tolerance {used_tol})"
        )
    return last, used_tol, True


# ── site point loading + coordinate validation ───────────────────────────────

def _load_site_points(conn: sqlite3.Connection):
    """Load ``sites`` rows as WGS84 points, dropping invalid coordinates.

    Returns ``(sites_gdf, skipped)`` where skipped is a list of
    ``{"id", "reason"}`` dicts. Rows are skipped when coordinates are missing
    (reason ``"missing_lat_lng"``) or fall outside PR's bbox (reason
    ``"outside_pr_bbox"``) — the latter also catches lat/lng-swapped rows.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    lon_min, lon_max, lat_min, lat_max = PR_BBOX
    rows = conn.execute("SELECT id, name, lat, lng FROM sites").fetchall()

    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for site_id, name, lat, lng in rows:
        if lat is None or lng is None:
            skipped.append({"id": site_id, "reason": "missing_lat_lng"})
            continue
        if not (lat_min <= lat <= lat_max and lon_min <= lng <= lon_max):
            skipped.append({"id": site_id, "reason": "outside_pr_bbox"})
            continue
        records.append(
            {"id": site_id, "name": name, "lat": lat, "lng": lng, "geometry": Point(lng, lat)}
        )

    if records:
        sites_gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=4326)
    else:
        sites_gdf = gpd.GeoDataFrame(
            columns=["id", "name", "lat", "lng", "geometry"], geometry="geometry", crs=4326
        )
    return sites_gdf, skipped


# ── download + layer build ───────────────────────────────────────────────────

def _download(url: str, dest: Path, timeout: int, retries: int = 3) -> tuple[int, str]:
    """Download ``url`` to ``dest`` (cached; reused if already present). Returns
    ``(bytes, sha256)`` of the file on disk."""
    import requests

    if dest.exists() and dest.stat().st_size > 0:
        log.info("using cached %s (%d bytes)", dest.name, dest.stat().st_size)
    else:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                log.info("downloading %s (attempt %d/%d)", url, attempt, retries)
                with requests.get(
                    url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT}
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
            raise RuntimeError(f"failed to download {url} after {retries} attempts") from last_exc

    return dest.stat().st_size, _sha256_file(dest)


def _build_layer_gdf(zip_path: Path, spec: dict[str, Any]):
    """Read a TIGER shapefile zip into a WGS84 GeoDataFrame with GEOID/NAME."""
    import geopandas as gpd

    gdf = gpd.read_file(f"zip://{zip_path.resolve()}")

    state_filter = spec.get("state_filter")
    if state_filter and "STATEFP" in gdf.columns:
        gdf = gdf[gdf["STATEFP"] == state_filter].copy()

    # Subset to the source GEOID/NAME columns *before* renaming, so a file that
    # already carries a NAME column (e.g. the county file has both NAME and
    # NAMELSAD) can't produce a duplicate NAME after the rename.
    geoid_field = spec["geoid_field"]
    name_field = spec["name_field"]
    subset = [col for col in (geoid_field, name_field) if col in gdf.columns] + ["geometry"]
    gdf = gdf[subset].copy()
    gdf = gdf.rename(columns={geoid_field: "GEOID", name_field: "NAME"})

    if gdf.crs is not None:
        gdf = gdf.to_crs(4326)
    return gdf


def _match_sites(conn, sites_gdf, muni_gdf, tract_gdf, write: bool) -> tuple[int, int]:
    """Point-in-polygon join sites → municipio/tract GEOIDs. Optionally persist.

    Returns ``(municipio_matched, tract_matched)`` counts."""
    import geopandas as gpd

    if sites_gdf.empty:
        return 0, 0

    points = sites_gdf[["id", "geometry"]]

    def _join(polys, out_col: str) -> dict[str, str]:
        right = polys[["GEOID", "geometry"]].rename(columns={"GEOID": out_col})
        joined = gpd.sjoin(points, right, how="left", predicate="within")
        joined = joined[~joined.index.duplicated(keep="first")]
        return {
            row_id: value
            for row_id, value in zip(joined["id"], joined[out_col])
            if value is not None and not _isnan(value)
        }

    muni_map = _join(muni_gdf, "municipio_geoid")
    tract_map = _join(tract_gdf, "tract_geoid")

    if write:
        for site_id, geoid in muni_map.items():
            conn.execute("UPDATE sites SET municipio_geoid=? WHERE id=?", (geoid, site_id))
        for site_id, geoid in tract_map.items():
            conn.execute("UPDATE sites SET tract_geoid=? WHERE id=?", (geoid, site_id))
        conn.commit()

    return len(muni_map), len(tract_map)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


# ── orchestration ────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    year = args.year
    cache_dir = Path(args.cache_dir)
    data_dir = Path(args.data_dir)
    base = TIGER_BASE.format(year=year)

    built: dict[str, Any] = {}
    manifest_layers: list[dict[str, Any]] = []
    layers_written: list[str] = []

    for layer, spec in LAYER_SPECS.items():
        filename = spec["tiger_filename"].format(year=year)
        url = f"{base}{spec['tiger_subdir']}/{filename}"
        zip_path = cache_dir / filename

        if args.max_bytes is not None:
            spec = {**spec, "max_bytes": args.max_bytes}
            LAYER_SPECS[layer]["max_bytes"] = args.max_bytes

        src_bytes, src_sha = _download(url, zip_path, args.timeout)
        gdf = _build_layer_gdf(zip_path, spec)
        payload, tolerance, oversized = _serialize_with_size_check(gdf, layer)
        built[layer] = gdf

        out_path = data_dir / f"{layer}.geojson"
        if not args.dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(payload)

        manifest_layers.append(
            {
                "layer": layer,
                "source": {
                    "url": url,
                    "filename": filename,
                    "sha256": src_sha,
                    "bytes": src_bytes,
                },
                "output": {
                    "path": str(out_path),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                    "feature_count": int(len(gdf)),
                    "oversized_warning": bool(oversized),
                    "simplify_tolerance": tolerance,
                },
            }
        )
        layers_written.append(layer)
        log.info(
            "built %s: %d features, %d bytes%s",
            layer,
            len(gdf),
            len(payload),
            " (OVERSIZED)" if oversized else "",
        )

    muni_matched = tract_matched = 0
    db_path = Path(args.db) if args.db else None
    if db_path and db_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            if _table_exists(conn, "sites"):
                ensure_sites_geoid_columns(conn)
                sites_gdf, skipped = _load_site_points(conn)
                if skipped:
                    log.info("skipped %d site rows with invalid coordinates", len(skipped))
                muni_matched, tract_matched = _match_sites(
                    conn, sites_gdf, built["municipios"], built["tracts"], write=not args.dry_run
                )
            else:
                log.info("sites table absent in %s; skipping GEOID join", db_path)
        finally:
            conn.close()
    else:
        log.info("no DB at %s; skipping GEOID join", db_path)

    manifest = {
        "ingestor": "ingest_tiger_pr.py",
        "year": year,
        "generated_utc": _utc_now(),
        "tiger_base": base,
        "layers": manifest_layers,
        "sites": {
            "municipio_matched": muni_matched,
            "tract_matched": tract_matched,
        },
    }
    if not args.dry_run:
        manifest_path = data_dir / "tiger" / str(year) / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        log.info("wrote manifest %s", manifest_path)

    summary = {
        "dry_run": bool(args.dry_run),
        "year": year,
        "layers_written": layers_written,
        "sites_municipio_matched": muni_matched,
        "sites_tract_matched": tract_matched,
    }
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest PR TIGER/Line geographies into GeoJSON")
    parser.add_argument("--year", type=int, default=2025, help="TIGER vintage year")
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parents[2] / "data"),
        help="Directory for <layer>.geojson outputs and tiger/<year>/manifest.json",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(Path(__file__).resolve().parents[2] / "data" / "tiger" / "cache"),
        help="Directory for cached raw TIGER zips (never committed)",
    )
    parser.add_argument(
        "--db",
        default=str(Path(__file__).resolve().parents[1] / "priis.db"),
        help="Path to priis.db for the site→GEOID join",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="Override the per-layer GeoJSON size budget",
    )
    parser.add_argument("--timeout", type=int, default=120, help="Per-download timeout (seconds)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and build everything but write no GeoJSON/manifest and no DB updates",
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
