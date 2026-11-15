#!/usr/bin/env python3
"""Materialize authoritative PR Grid V2 bindings from exact source coordinates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from spiderweb.grid_v2_source_coordinates import (  # noqa: E402
    bind_exact_source_points,
    flatten_source_binding_rows,
    projection_audit_rows,
    source_binding_receipt,
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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--level", choices=("L0", "L1", "L2", "L3"), required=True)
    parser.add_argument("--bindings-out", type=Path, required=True)
    parser.add_argument("--projection-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    results = bind_exact_source_points(_read_jsonl(args.input), level=args.level)
    bindings = flatten_source_binding_rows(results)
    projections = projection_audit_rows(results)

    _write_jsonl(args.bindings_out, bindings)
    _write_jsonl(args.projection_out, projections)

    receipt = source_binding_receipt(results)
    receipt.update(
        {
            "Input_SHA256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
            "Input_Bytes": args.input.stat().st_size,
            "Binding_Output_SHA256": hashlib.sha256(
                args.bindings_out.read_bytes()
            ).hexdigest(),
            "Binding_Output_Bytes": args.bindings_out.stat().st_size,
            "Projection_Output_SHA256": hashlib.sha256(
                args.projection_out.read_bytes()
            ).hexdigest(),
            "Projection_Output_Bytes": args.projection_out.stat().st_size,
            "Receipt_State": "PASS",
        }
    )
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
