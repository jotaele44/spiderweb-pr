"""
EarthGPT iOS — JSONL validator.

Counts valid and invalid rows in a JSONL file.
Critical for iOS resumable execution.

Usage:
    python -m scripts.validate_jsonl outputs/geo_queue.jsonl
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import count_jsonl
from earthgpt.log_utils import log


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.validate_jsonl <path.jsonl>")
        sys.exit(1)

    path = sys.argv[1]
    valid, invalid = count_jsonl(path)
    total = valid + invalid

    log(f"File   : {path}")
    log(f"Valid  : {valid}")
    log(f"Invalid: {invalid}")
    log(f"Total  : {total}")

    if invalid > 0:
        log(f"WARNING: {invalid} malformed lines detected", prefix="WARN")
    else:
        log("All lines valid.")


if __name__ == "__main__":
    main()
