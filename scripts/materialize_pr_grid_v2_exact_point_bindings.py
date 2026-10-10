#!/usr/bin/env python3
"""Materialize authoritative PR grid V2 bindings from exact EPSG:6566 points."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from spiderweb.grid_v2_bindings import (  # noqa: E402
    bind_exact_points,
    binding_receipt,
    flatten_binding_rows,
)


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise SystemExit(f"{path}:{lineno}: expected JSON object")
            rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--level", choices=("L0", "L1", "L2", "L3"), required=True)
    parser.add_argument("--bindings-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    results = bind_exact_points(_read_jsonl(args.input), level=args.level)
    bindings = flatten_binding_rows(results)

    args.bindings_out.parent.mkdir(parents=True, exist_ok=True)
    with args.bindings_out.open("w", encoding="utf-8") as handle:
        for row in bindings:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    receipt = binding_receipt(results)
    receipt["Binding_Output"] = str(args.bindings_out)
    receipt["Receipt_State"] = "PASS"
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
