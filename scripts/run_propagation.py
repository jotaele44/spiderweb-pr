"""
EarthGPT iOS — Propagation stage runner.

Usage:
    python -m scripts.run_propagation --phase1 outputs/phase1_tiles.jsonl --out outputs/propagated_tiles.jsonl --neighbors 8
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.propagation import propagate_scores
from earthgpt.log_utils import log
from earthgpt import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Propagation stage")
    parser.add_argument("--phase1", required=True, help="Phase1 JSONL input")
    parser.add_argument("--out", required=True, help="Output JSONL")
    parser.add_argument("--neighbors", type=int, default=8)
    parser.add_argument("--zoom", type=int, default=config.DEFAULT_ZOOM)
    args = parser.parse_args()

    nodes = read_jsonl(args.phase1)
    log(f"Loaded {len(nodes)} nodes for propagation")

    if not nodes:
        log("No nodes to propagate — writing empty output.")
        write_jsonl(args.out, [])
        return

    result = propagate_scores(nodes, zoom=args.zoom, n_neighbors=args.neighbors)
    log(f"Propagation produced {len(result)} nodes")

    write_jsonl(args.out, result)
    log(f"Propagated output written to: {args.out}")


if __name__ == "__main__":
    main()
