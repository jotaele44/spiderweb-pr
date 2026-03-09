"""
EarthGPT iOS — Geo grid queue generator.

Generates a JSONL queue file from an optional CSV grid file
or from a built-in fallback test grid.

Usage:
    python -m scripts.make_geo_grid_queue --out outputs/geo_queue.jsonl
    python -m scripts.make_geo_grid_queue --csv grid.csv --out outputs/geo_queue.jsonl

CSV format expected:
    lat,lon   (with header row)
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import write_jsonl
from earthgpt.tile_utils import lat_lon_to_tile, tile_center, node_id_for
from earthgpt.log_utils import log, warn
from earthgpt import config


# ── Fallback test grid (Puerto Rico bounding box) ────────────────────────────
_PR_BBOX = {
    "lat_min": 17.88,
    "lat_max": 18.55,
    "lon_min": -67.30,
    "lon_max": -65.20,
}
_FALLBACK_STEP_DEG = 0.05  # ~5.5 km at these latitudes
_FALLBACK_ZOOM = config.DEFAULT_ZOOM


def _fallback_grid() -> list:
    rows = []
    lat = _PR_BBOX["lat_min"]
    idx = 0
    while lat <= _PR_BBOX["lat_max"]:
        lon = _PR_BBOX["lon_min"]
        while lon <= _PR_BBOX["lon_max"]:
            x, y = lat_lon_to_tile(lat, lon, _FALLBACK_ZOOM)
            nid = node_id_for(x, y, _FALLBACK_ZOOM)
            rows.append({"node_id": nid, "lat": round(lat, 6), "lon": round(lon, 6)})
            idx += 1
            lon += _FALLBACK_STEP_DEG
        lat += _FALLBACK_STEP_DEG
    return rows


def _load_csv_grid(csv_path: str) -> list:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
        for i, raw_row in enumerate(reader):
            row = {k.strip().lower(): v.strip() for k, v in raw_row.items()}
            try:
                lat = float(row.get("lat", row.get("latitude", "")))
                lon = float(row.get("lon", row.get("longitude", "")))
            except ValueError:
                warn(f"Skipping malformed CSV row {i+2}: {raw_row}")
                continue
            zoom = int(row.get("zoom", _FALLBACK_ZOOM))
            x, y = lat_lon_to_tile(lat, lon, zoom)
            nid = row.get("node_id") or node_id_for(x, y, zoom)
            rows.append({"node_id": nid, "lat": round(lat, 6), "lon": round(lon, 6)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate geo grid queue JSONL")
    parser.add_argument("--csv", default=None, help="Path to input CSV grid file")
    parser.add_argument("--out", required=True, help="Output JSONL queue path")
    args = parser.parse_args()

    if args.csv:
        log(f"Loading grid from CSV: {args.csv}")
        rows = _load_csv_grid(args.csv)
        log(f"Loaded {len(rows)} nodes from CSV")
    else:
        log("No CSV provided — using fallback Puerto Rico test grid")
        rows = _fallback_grid()
        log(f"Generated {len(rows)} nodes from fallback grid")

    write_jsonl(args.out, rows)
    log(f"Queue written to: {args.out}")


if __name__ == "__main__":
    main()
