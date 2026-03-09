"""
EarthGPT iOS — Target ranker runner.

Reads corridor candidates and produces a ranked target list.

Usage:
    python -m scripts.run_target_ranker --corridors outputs/corridor_graph.jsonl --out outputs/ranked_targets.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.target_ranker import run_target_ranker
from earthgpt.log_utils import log, warn


def main() -> None:
    parser = argparse.ArgumentParser(description="Target ranker")
    parser.add_argument("--corridors", required=True, help="Corridor JSONL input")
    parser.add_argument("--out", required=True, help="Output ranked JSONL")
    parser.add_argument("--min_score", type=float, default=0.2)
    parser.add_argument("--min_nodes", type=int, default=1)
    args = parser.parse_args()

    candidates = read_jsonl(args.corridors)
    log(f"Loaded {len(candidates)} corridor candidates")

    if not candidates:
        warn("No candidates — writing empty output.")
        write_jsonl(args.out, [])
        return

    ranked = run_target_ranker(candidates, min_score=args.min_score, min_nodes=args.min_nodes)
    log(f"Ranked targets: {len(ranked)}")

    write_jsonl(args.out, ranked)
    log(f"Ranked targets written to: {args.out}")


if __name__ == "__main__":
    main()
