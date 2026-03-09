"""
EarthGPT iOS — Seam reconstruction stage.

Reads phase1 JSONL and writes seam records for adjacent anomalous tiles.

Usage:
    python -m scripts.reconstruct_seams --in outputs/phase1_tiles.jsonl --out outputs/seams.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.seam_graph import build_seam_graph
from earthgpt.log_utils import log
from earthgpt import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Seam reconstruction")
    parser.add_argument("--in", dest="input", required=True, help="Phase1 JSONL")
    parser.add_argument("--out", required=True, help="Output seams JSONL")
    parser.add_argument("--zoom", type=int, default=config.DEFAULT_ZOOM)
    parser.add_argument("--threshold", type=float, default=config.ANOMALY_THRESHOLD)
    args = parser.parse_args()

    nodes = read_jsonl(args.input)
    log(f"Loaded {len(nodes)} nodes from {args.input}")

    seams = build_seam_graph(nodes, zoom=args.zoom, threshold=args.threshold)
    log(f"Detected {len(seams)} seams")

    write_jsonl(args.out, seams)
    log(f"Seams written to: {args.out}")


if __name__ == "__main__":
    main()
