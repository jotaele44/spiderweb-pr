"""
EarthGPT iOS — Quarter-grid queue generator.

Generates a queue for one geographic quarter of the full grid,
useful for splitting work across multiple iOS sessions.

Usage:
    python -m scripts.make_quarter_queue --quarter NW --out outputs/geo_queue_nw.jsonl
    python -m scripts.make_quarter_queue --quarter NW --csv grid.csv --out outputs/geo_queue_nw.jsonl
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import read_jsonl, write_jsonl
from earthgpt.log_utils import log, warn
from scripts.make_geo_grid_queue import _fallback_grid, _load_csv_grid


_QUARTERS = {
    "NW": lambda row: row["lat"] >= 18.22 and row["lon"] <= -66.55,
    "NE": lambda row: row["lat"] >= 18.22 and row["lon"] > -66.55,
    "SW": lambda row: row["lat"] < 18.22 and row["lon"] <= -66.55,
    "SE": lambda row: row["lat"] < 18.22 and row["lon"] > -66.55,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarter-grid queue generator")
    parser.add_argument("--quarter", choices=list(_QUARTERS), required=True)
    parser.add_argument("--csv", default=None, help="Input CSV grid path")
    parser.add_argument("--out", required=True, help="Output JSONL path")
    args = parser.parse_args()

    if args.csv:
        all_rows = _load_csv_grid(args.csv)
    else:
        all_rows = _fallback_grid()

    fn = _QUARTERS[args.quarter]
    filtered = [r for r in all_rows if fn(r)]
    log(f"Quarter {args.quarter}: {len(filtered)}/{len(all_rows)} nodes")
    write_jsonl(args.out, filtered)
    log(f"Written to {args.out}")


if __name__ == "__main__":
    main()
