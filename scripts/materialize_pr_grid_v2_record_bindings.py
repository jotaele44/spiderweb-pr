#!/usr/bin/env python3
"""Materialize one mixed, authority-side PR Grid V2 record migration denominator."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from spiderweb.geographic_grid_v2 import GridV2Error  # noqa: E402
from spiderweb.grid_v2_record_migration import (  # noqa: E402
    flatten_binding_rows,
    migrate_records,
    migration_audit_rows,
    migration_receipt,
)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GridV2Error(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise GridV2Error(f"{path}:{lineno}: JSONL row must be an object")
        rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--level", choices=("L0", "L1", "L2", "L3"), required=True)
    parser.add_argument("--bindings-out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    try:
        results = migrate_records(_load_jsonl(args.input), level=args.level)
        bindings = flatten_binding_rows(results)
        audit = migration_audit_rows(results)
        _write_jsonl(args.bindings_out, bindings)
        _write_jsonl(args.audit_out, audit)
    except (OSError, ValueError, TypeError, GridV2Error) as exc:
        parser.exit(2, f"FAIL_CLOSED: {exc}\n")

    receipt = migration_receipt(results)
    receipt.update(
        {
            "Grid_Level": args.level,
            "Input_SHA256": _sha256(args.input),
            "Input_Bytes": args.input.stat().st_size,
            "Binding_Output_SHA256": _sha256(args.bindings_out),
            "Binding_Output_Bytes": args.bindings_out.stat().st_size,
            "Audit_Output_SHA256": _sha256(args.audit_out),
            "Audit_Output_Bytes": args.audit_out.stat().st_size,
            "Receipt_State": "PASS",
            "Promotion_State": "CANDIDATE_NOT_CANONICAL",
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
