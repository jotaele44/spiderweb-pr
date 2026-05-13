"""
EarthGPT iOS — Candidate refinement.

Applies quality filters to corridor candidates.

Usage:
    python -m scripts.refine_candidates --tile_metrics outputs/phase1_tiles.jsonl --tile_index PR_grid_cells_pixel_index_quarter.csv --out outputs/refined_candidates.jsonl
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.log_utils import log, warn


def load_tile_index(csv_path: str) -> dict:
    """Load tile index CSV into a dict keyed by node_id."""
    idx = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                nid = row.get("node_id", "").strip()
                if nid:
                    idx[nid] = {k.strip(): v.strip() for k, v in row.items()}
    except FileNotFoundError:
        warn(f"Tile index not found: {csv_path} — proceeding without index")
    return idx


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine candidates")
    parser.add_argument("--tile_metrics", required=True, help="Phase1 JSONL")
    parser.add_argument("--tile_index", default=None, help="Optional CSV tile index")
    parser.add_argument("--out", required=True, help="Output JSONL")
    parser.add_argument("--min_score", type=float, default=0.3)
    args = parser.parse_args()

    nodes = read_jsonl(args.tile_metrics)
    index = load_tile_index(args.tile_index) if args.tile_index else {}

    refined = []
    for n in nodes:
        if float(n.get("score", 0.0)) < args.min_score:
            continue
        nid = n.get("node_id", "")
        if nid in index:
            n["index_metadata"] = index[nid]
        refined.append(n)

    log(f"Refined: {len(refined)} / {len(nodes)} nodes pass threshold {args.min_score}")
    write_jsonl(args.out, refined)
    log(f"Written to: {args.out}")


if __name__ == "__main__":
    main()
