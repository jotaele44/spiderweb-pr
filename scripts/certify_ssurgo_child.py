#!/usr/bin/env python3
"""Certify one SSURGO component-child response against a frozen COKEY denominator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.ssurgo_chain import certify_child_table_response


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--stage3-plan", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.stage3_plan.read_text(encoding="utf-8"))
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    parent = (plan.get("ssurgo_cokey_denominator") or {}).get("cokeys")
    if not isinstance(parent, list):
        raise SystemExit("FAIL: stage3 plan lacks COKEY denominator")
    contracts = {
        row.get("table"): row
        for row in (plan.get("child_table_denominator") or {}).get("tables", [])
        if isinstance(row, dict)
    }
    if args.table not in contracts:
        raise SystemExit(f"FAIL: table not in stage3 child denominator: {args.table}")
    result = certify_child_table_response(
        raw=args.raw.read_bytes(),
        receipt=receipt,
        contract=contracts[args.table],
        certified_cokeys=[str(value) for value in parent],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
