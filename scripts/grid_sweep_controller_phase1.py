"""
EarthGPT iOS — Phase 1 grid sweep controller.

Reads a queue JSONL, fetches tiles, computes metrics, writes phase1 JSONL.
Resumes safely if output already contains processed nodes.

Usage:
    python -m scripts.grid_sweep_controller_phase1 --queue outputs/geo_queue.jsonl --out outputs/phase1_tiles.jsonl
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import iter_jsonl, append_jsonl, load_done_ids
from earthgpt.pipeline import analyze_node
from earthgpt.tile_utils import lat_lon_to_tile
from earthgpt.log_utils import log, warn, error, progress
from earthgpt import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 sweep controller")
    parser.add_argument("--queue", required=True, help="Input queue JSONL")
    parser.add_argument("--out", required=True, help="Output phase1 JSONL")
    parser.add_argument("--zoom", type=int, default=config.DEFAULT_ZOOM)
    args = parser.parse_args()

    queue = list(iter_jsonl(args.queue))
    if not queue:
        log("Queue is empty — nothing to process.")
        return

    done_ids = load_done_ids(args.out)
    log(f"Queue: {len(queue)} nodes | Already done: {len(done_ids)}")

    remaining = [q for q in queue if q.get("node_id") not in done_ids]
    log(f"Remaining: {len(remaining)} nodes")

    for i, q_row in enumerate(remaining, 1):
        node_id = q_row.get("node_id", f"node_{i}")
        lat = float(q_row.get("lat", 0.0))
        lon = float(q_row.get("lon", 0.0))
        zoom = int(q_row.get("zoom", args.zoom))

        x, y = lat_lon_to_tile(lat, lon, zoom)

        try:
            result = analyze_node(x=x, y=y, zoom=zoom, lat=lat, lon=lon)
            result["node_id"] = node_id
        except Exception as exc:
            error(f"Node {node_id} exception: {exc}")
            result = {
                "node_id": node_id,
                "lat": lat,
                "lon": lon,
                "x": x,
                "y": y,
                "zoom": zoom,
                "score": 0.0,
                "decision": "error",
                "risk_final_v2_0_100": 0.0,
                "status": "exception",
                "error": str(exc),
                "ts_epoch": int(time.time()),
            }

        append_jsonl(args.out, result)
        progress(i, len(remaining), interval=config.PHASE1_PRINT_INTERVAL, label="phase1")

    log(f"Phase 1 complete. Output: {args.out}")


if __name__ == "__main__":
    main()
