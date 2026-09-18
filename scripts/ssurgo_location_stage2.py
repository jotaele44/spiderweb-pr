#!/usr/bin/env python3
"""Build SSURGO dependent stage-2 SDA plan from preserved MapunitPoly bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.ssurgo_chain import write_stage2_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=Path, required=True, help="Original LOCATION_QUERY JSON")
    parser.add_argument("--mapunitpoly-raw", type=Path, required=True)
    parser.add_argument("--mapunitpoly-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    query = json.loads(args.query.read_text(encoding="utf-8"))
    plan = write_stage2_plan(
        query=query,
        mapunitpoly_raw_path=args.mapunitpoly_raw,
        mapunitpoly_receipt_path=args.mapunitpoly_receipt,
        output=args.output,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
