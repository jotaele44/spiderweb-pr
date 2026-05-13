"""
EarthGPT iOS — Multiscale anomaly pass.

Re-evaluates phase1 candidates at multiple zoom levels
to measure zoom persistence.

Usage:
    python -m scripts.run_multiscale --candidates outputs/phase1_tiles.jsonl --out outputs/phase2_multiscale.jsonl --zooms 15,16,17
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import iter_jsonl, read_jsonl, append_jsonl, load_done_ids
from earthgpt.tiles import fetch_tile_rgb_xy
from earthgpt.metrics import compute_node_metrics
from earthgpt.tile_utils import lat_lon_to_tile
from earthgpt.log_utils import log, error, progress
from earthgpt import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Multiscale anomaly pass")
    parser.add_argument("--candidates", required=True, help="Phase1 JSONL")
    parser.add_argument("--out", required=True, help="Output JSONL")
    parser.add_argument("--zooms", default=",".join(str(z) for z in config.MULTISCALE_ZOOMS))
    parser.add_argument("--risk", type=float, default=config.RISK_THRESHOLD)
    parser.add_argument("--resume", action="store_true", help="Resume from existing output")
    args = parser.parse_args()

    zooms = [int(z) for z in args.zooms.split(",")]
    candidates = [
        r for r in iter_jsonl(args.candidates)
        if float(r.get("risk_final_v2_0_100", 0.0)) >= args.risk
    ]
    log(f"Multiscale candidates: {len(candidates)} at zooms {zooms}")

    done_ids = load_done_ids(args.out) if args.resume else set()

    for i, row in enumerate(candidates, 1):
        node_id = row.get("node_id", f"node_{i}")
        if node_id in done_ids:
            continue

        lat = float(row.get("lat", 0.0))
        lon = float(row.get("lon", 0.0))

        images_by_zoom = {}
        for z in zooms:
            x, y = lat_lon_to_tile(lat, lon, z)
            images_by_zoom[z] = fetch_tile_rgb_xy(x, y, z)

        try:
            result = compute_node_metrics(images_by_zoom)
        except Exception as exc:
            error(f"Multiscale node {node_id}: {exc}")
            result = {"status": "exception", "error": str(exc),
                      "score": 0.0, "decision": "error",
                      "risk_final_v2_0_100": 0.0}

        result.update({
            "node_id": node_id,
            "lat": lat,
            "lon": lon,
            "zooms_evaluated": zooms,
            "ts_epoch": int(time.time()),
        })
        append_jsonl(args.out, result)
        progress(i, len(candidates), interval=config.PHASE2_PRINT_INTERVAL, label="multiscale")

    log(f"Multiscale complete. Output: {args.out}")


if __name__ == "__main__":
    main()
