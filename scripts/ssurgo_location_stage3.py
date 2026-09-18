#!/usr/bin/env python3
"""Build SSURGO dependent stage-3 child-table plan from preserved component bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.ssurgo_chain import build_stage3_child_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--component-raw", type=Path, required=True)
    parser.add_argument("--component-receipt", type=Path, required=True)
    parser.add_argument(
        "--children",
        type=Path,
        default=Path("configs/ssurgo_component_children.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    query = json.loads(args.query.read_text(encoding="utf-8"))
    receipt = json.loads(args.component_receipt.read_text(encoding="utf-8"))
    contract = json.loads(args.children.read_text(encoding="utf-8"))
    result = build_stage3_child_plan(
        query=query,
        component_raw=args.component_raw.read_bytes(),
        component_receipt=receipt,
        child_contract=contract,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
