"""
EarthGPT iOS — Resume queue builder.

Generates a new queue JSONL from the difference between a full queue
and an existing phase1 output — enabling safe resume after interruption.

Usage:
    python -m scripts.make_resume_queue --queue outputs/geo_queue.jsonl --done outputs/phase1_tiles.jsonl --out outputs/resume_queue.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl, load_done_ids
from earthgpt.log_utils import log


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume queue generator")
    parser.add_argument("--queue", required=True, help="Original queue JSONL")
    parser.add_argument("--done", required=True, help="Completed phase1 JSONL")
    parser.add_argument("--out", required=True, help="Output resume queue JSONL")
    args = parser.parse_args()

    full_queue = read_jsonl(args.queue)
    done_ids = load_done_ids(args.done)

    remaining = [q for q in full_queue if q.get("node_id") not in done_ids]
    log(f"Full queue: {len(full_queue)} | Done: {len(done_ids)} | Remaining: {len(remaining)}")

    write_jsonl(args.out, remaining)
    log(f"Resume queue written to: {args.out}")


if __name__ == "__main__":
    main()
