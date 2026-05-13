"""
EarthGPT iOS — Interactive JSONL inspector.

Prints a summary of any pipeline JSONL output file.

Usage:
    python -m scripts.run_inspector outputs/phase1_tiles.jsonl
    python -m scripts.run_inspector outputs/phase1_tiles.jsonl --top 5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl
from earthgpt.log_utils import log


def main() -> None:
    parser = argparse.ArgumentParser(description="JSONL inspector")
    parser.add_argument("file", help="JSONL file to inspect")
    parser.add_argument("--top", type=int, default=10, help="Top N rows by score")
    parser.add_argument("--field", default="score", help="Field to sort by")
    args = parser.parse_args()

    rows = read_jsonl(args.file)
    log(f"Rows: {len(rows)}")

    if not rows:
        log("Empty file.")
        return

    # Field summary
    fields = set()
    for r in rows:
        fields.update(r.keys())
    log(f"Fields: {', '.join(sorted(fields))}")

    # Top N by score field
    scored = [(r.get(args.field, 0.0), r) for r in rows]
    scored.sort(key=lambda t: float(t[0]) if t[0] is not None else 0.0, reverse=True)

    log(f"\nTop {args.top} by '{args.field}':")
    for score, row in scored[: args.top]:
        nid = row.get("node_id", row.get("corridor_id", "?"))
        lat = row.get("lat") or row.get("centroid_lat", "?")
        lon = row.get("lon") or row.get("centroid_lon", "?")
        print(f"  {nid:30s} {args.field}={score:6.4f}  lat={lat}  lon={lon}")


if __name__ == "__main__":
    main()
