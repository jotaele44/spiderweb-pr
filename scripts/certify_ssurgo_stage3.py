#!/usr/bin/env python3
"""Certify all SSURGO Stage-3 component-child responses in one bounded receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.ssurgo_chain import certify_stage3_fetch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage3-plan", type=Path, required=True)
    parser.add_argument("--fetch-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(
            f"FAIL: SSURGO Stage-3 certification already exists: {args.output}"
        )

    plan = json.loads(args.stage3_plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.fetch_receipt.read_text(encoding="utf-8"))
    result = certify_stage3_fetch(
        stage3_plan=plan,
        fetch_receipt=receipt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "state": result["state"],
        "parent_cokey_count": result["parent_cokey_count"],
        "child_table_count": result["child_table_count"],
        "total_child_rows": result["total_child_rows"],
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
