#!/usr/bin/env python3
"""Independently audit vNext artifacts, without release promotion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spiderweb.geographic_grid_v2 import GridV2Error  # noqa: E402
from spiderweb.grid_v2_binding_artifact_audit import audit_binding_artifacts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = audit_binding_artifacts(
        input_path=args.input, manifest_path=args.source_manifest,
        bindings_path=args.bindings, receipt_path=args.receipt,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GridV2Error, ValueError, OSError) as exc:
        print(f"FAIL_CLOSED_AUDIT: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
