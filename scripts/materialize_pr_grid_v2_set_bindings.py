#!/usr/bin/env python3
"""Materialize administrative and derived PR grid V2 set bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from spiderweb.geographic_grid_v2 import GridV2Error  # noqa: E402
from spiderweb.grid_v2_geometry_bindings import (  # noqa: E402
    bind_set_geometries,
    flatten_set_binding_rows,
    set_binding_receipt,
)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise GridV2Error(f"line {lineno}: JSONL row must be an object")
        rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--level", choices=("L0", "L1", "L2", "L3"), required=True)
    parser.add_argument("--bindings-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    try:
        rows = _load_jsonl(args.input)
        results = bind_set_geometries(rows, level=args.level)
        bindings = flatten_set_binding_rows(results)
    except (OSError, json.JSONDecodeError, GridV2Error, ValueError) as exc:
        parser.exit(2, f"FAIL_CLOSED: {exc}\n")

    args.bindings_out.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        for row in bindings
    )
    args.bindings_out.write_text(payload, encoding="utf-8")

    receipt = set_binding_receipt(results)
    receipt.update(
        {
            "Input_SHA256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
            "Input_Bytes": args.input.stat().st_size,
            "Binding_Output_SHA256": hashlib.sha256(
                args.bindings_out.read_bytes()
            ).hexdigest(),
            "Binding_Output_Bytes": args.bindings_out.stat().st_size,
            "Binding_Output": str(args.bindings_out),
            "Receipt_State": "PASS",
        }
    )
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
