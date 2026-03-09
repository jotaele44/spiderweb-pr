"""
EarthGPT iOS — GeoJSON export stage.

Converts ranked_targets.jsonl → targets.geojson.

Usage:
    python -m scripts.export_ranked_geojson --in outputs/ranked_targets.jsonl --out outputs/targets.geojson
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import iter_jsonl
from earthgpt.log_utils import log, warn


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ranked targets to GeoJSON")
    parser.add_argument("--in", dest="input", required=True, help="Ranked JSONL input")
    parser.add_argument("--out", required=True, help="Output GeoJSON path")
    args = parser.parse_args()

    features = []
    skipped = 0

    for row in iter_jsonl(args.input):
        lat = row.get("centroid_lat") or row.get("lat")
        lon = row.get("centroid_lon") or row.get("lon")
        score = row.get("rank_score") or row.get("score")

        try:
            lat = float(lat)
            lon = float(lon)
            score = float(score)
        except (TypeError, ValueError):
            warn(f"Skipping row with invalid lat/lon/score: {row.get('corridor_id', row.get('node_id', '?'))}")
            skipped += 1
            continue

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            warn(f"Invalid coordinates ({lat},{lon}) — skipping")
            skipped += 1
            continue

        properties = {k: v for k, v in row.items()
                      if k not in ("centroid_lat", "centroid_lon")}

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": properties,
        })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh, indent=2, ensure_ascii=False)

    log(f"Exported {len(features)} features to {args.out} ({skipped} skipped)")


if __name__ == "__main__":
    main()
