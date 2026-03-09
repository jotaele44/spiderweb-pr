"""
EarthGPT iOS — Phase 2 safe sweep controller.

Runs a second pass over phase1 anomalies at higher zoom levels.
Resumes safely; tolerates partial outputs.

Usage:
    python -m scripts.grid_sweep_controller_phase2_safe --phase1 outputs/phase1_tiles.jsonl --out outputs/phase2_tiles.jsonl
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import iter_jsonl, append_jsonl, load_done_ids
from earthgpt.pipeline import analyze_node
from earthgpt.tile_utils import lat_lon_to_tile
from earthgpt.log_utils import log, error, progress
from earthgpt import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 safe sweep controller")
    parser.add_argument("--phase1", required=True, help="Phase1 JSONL input")
    parser.add_argument("--out", required=True, help="Output JSONL")
    parser.add_argument("--risk", type=float, default=config.RISK_THRESHOLD,
                        help="Min risk_final_v2_0_100 to include")
    parser.add_argument("--zooms", default="16,17", help="Comma-separated zoom levels")
    args = parser.parse_args()

    zooms = [int(z) for z in args.zooms.split(",")]
    candidates = [
        r for r in iter_jsonl(args.phase1)
        if float(r.get("risk_final_v2_0_100", 0.0)) >= args.risk
    ]
    log(f"Phase2 candidates above risk={args.risk}: {len(candidates)}")

    if not candidates:
        log("No candidates — writing empty output.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).touch()
        return

    done_ids = load_done_ids(args.out, id_field="node_id")

    total = len(candidates) * len(zooms)
    processed = 0

    for row in candidates:
        for zoom in zooms:
            node_id = f"{row.get('node_id', 'unk')}@z{zoom}"
            if node_id in done_ids:
                processed += 1
                continue
            lat = float(row.get("lat", 0.0))
            lon = float(row.get("lon", 0.0))
            x, y = lat_lon_to_tile(lat, lon, zoom)
            try:
                result = analyze_node(x=x, y=y, zoom=zoom, lat=lat, lon=lon)
                result["node_id"] = node_id
                result["parent_node_id"] = row.get("node_id", "")
            except Exception as exc:
                error(f"Phase2 node {node_id}: {exc}")
                result = {
                    "node_id": node_id,
                    "status": "exception",
                    "error": str(exc),
                    "ts_epoch": int(time.time()),
                }
            append_jsonl(args.out, result)
            processed += 1
            progress(processed, total, interval=config.PHASE2_PRINT_INTERVAL, label="phase2")

    log(f"Phase 2 complete. Output: {args.out}")


if __name__ == "__main__":
    main()
