#!/usr/bin/env python3
"""Provisional exact EPSG:6566 polygon, line, point binding materializer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spiderweb.geographic_grid_v2 import GridV2Error  # noqa: E402
from spiderweb.grid_v2_bindings_vnext import (  # noqa: E402
    bind_exact_geometries, binding_receipt_vnext, validate_schema_pins,
)


def read_jsonl(path: Path) -> list[dict]:
    results = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(
                    GridV2Error("nonfinite input constant")))
            except (ValueError, GridV2Error) as exc:
                raise GridV2Error(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise GridV2Error(f"{path}:{line_no}: expected object")
            results.append(row)
    return results


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--level", choices=("L0", "L1", "L2", "L3"), required=True)
    parser.add_argument("--bindings-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    if args.bindings_out.resolve() == args.receipt_out.resolve():
        raise GridV2Error("binding output and receipt cannot share path")
    if args.input.resolve() in (args.bindings_out.resolve(), args.receipt_out.resolve()):
        raise GridV2Error("input and output paths must be distinct")
    validate_schema_pins()
    results = bind_exact_geometries(read_jsonl(args.input), level=args.level)
    lines = [
        json.dumps(b, sort_keys=True, separators=(",", ":"), allow_nan=False)
        for result in results for b in result.bindings
    ]
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    receipt = binding_receipt_vnext(results)
    receipt.update({
        "Input_SHA256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "Binding_Output_SHA256": hashlib.sha256(payload).hexdigest(),
        "Binding_Output_Bytes": len(payload),
        "Receipt_State": "PROVISIONAL",
    })
    rpayload = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)
                + "\n").encode("utf-8")
    # Outputs are independently atomic. Any interrupted two-file promotion is
    # detected by the receipt's binding hash; never trust output alone.
    atomic_bytes(args.bindings_out, payload)
    atomic_bytes(args.receipt_out, rpayload)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GridV2Error, ValueError, OSError) as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
