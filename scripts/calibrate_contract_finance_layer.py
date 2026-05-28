#!/usr/bin/env python3
"""Generate a calibration report for Contract-Finance adapter/layer outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from readiness.contract_finance_calibration import calibrate_contract_finance_layer  # noqa: E402
from readiness.contract_finance_layer import ContractFinanceLayerError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Directory with contract-finance adapter/layer outputs")
    parser.add_argument("--out", default=None, help="Optional report path; default writes inside --input")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = calibrate_contract_finance_layer(args.input, args.out)
    except ContractFinanceLayerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
