"""
EarthGPT iOS — Grid coverage checker.

Compares a queue JSONL against a phase1 output to report coverage.

Usage:
    python -m scripts.grid_coverage_check --queue outputs/geo_queue.jsonl --phase1 outputs/phase1_tiles.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, load_done_ids
from earthgpt.log_utils import log


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid coverage check")
    parser.add_argument("--queue", required=True, help="Queue JSONL")
    parser.add_argument("--phase1", required=True, help="Phase1 JSONL")
    args = parser.parse_args()

    queue = read_jsonl(args.queue)
    done_ids = load_done_ids(args.phase1)

    total = len(queue)
    done = sum(1 for q in queue if q.get("node_id") in done_ids)
    remaining = total - done
    pct = 100.0 * done / total if total > 0 else 0.0

    log(f"Queue    : {total} nodes")
    log(f"Done     : {done} ({pct:.1f}%)")
    log(f"Remaining: {remaining}")


if __name__ == "__main__":
    main()
