"""
EarthGPT iOS — Cascade refinement.

Multi-pass refinement: raises threshold progressively to surface
the highest-confidence anomaly candidates.

Usage:
    python -m scripts.cascade_refine --tile_metrics outputs/phase1_tiles.jsonl --tile_index PR_grid_cells_pixel_index_quarter.csv --out outputs/refined_candidates.jsonl
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.log_utils import log


_CASCADE_THRESHOLDS = [0.25, 0.35, 0.45, 0.55]


def main() -> None:
    parser = argparse.ArgumentParser(description="Cascade refinement")
    parser.add_argument("--tile_metrics", required=True, help="Phase1 JSONL")
    parser.add_argument("--tile_index", default=None, help="Optional CSV tile index")
    parser.add_argument("--out", required=True, help="Output JSONL")
    args = parser.parse_args()

    nodes = read_jsonl(args.tile_metrics)
    index = {}
    if args.tile_index:
        try:
            with open(args.tile_index, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    nid = (row.get("node_id") or "").strip()
                    if nid:
                        index[nid] = {k.strip(): v.strip() for k, v in row.items()}
        except FileNotFoundError:
            log(f"Tile index not found: {args.tile_index} — skipping")

    best: list = nodes
    for thresh in _CASCADE_THRESHOLDS:
        filtered = [n for n in best if float(n.get("score", 0.0)) >= thresh]
        if len(filtered) == 0:
            break
        best = filtered
        log(f"Cascade pass @ {thresh}: {len(best)} nodes remain")

    for n in best:
        nid = n.get("node_id", "")
        if nid in index:
            n["index_metadata"] = index[nid]

    write_jsonl(args.out, best)
    log(f"Cascade refined: {len(best)} nodes written to {args.out}")


if __name__ == "__main__":
    main()
