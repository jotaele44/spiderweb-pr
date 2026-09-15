#!/usr/bin/env python3
"""Build the SpiderWeb contract/finance scored layer from adapter outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from readiness.contract_finance_layer import (  # noqa: E402
    ContractFinanceLayerError,
    build_contract_finance_layer,
)
from readiness.contract_finance_manifest_gate import (  # noqa: E402
    ContractFinanceManifestGateError,
    validate_contract_finance_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Directory containing moneysweep-pr adapter outputs")
    parser.add_argument("--out", default=None, help="Output directory for scored layer artifacts; default: --input")
    parser.add_argument(
        "--artifact-manifest",
        default=None,
        help="Optional moneysweep-pr artifact_manifest.json path. When supplied, the manifest gate must pass before scoring.",
    )
    parser.add_argument(
        "--expected-producer-commit",
        default=None,
        help="Exact MoneySweep commit expected by this run. Required whenever --artifact-manifest is supplied.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.artifact_manifest) != bool(args.expected_producer_commit):
        print(
            "ERROR: --artifact-manifest and --expected-producer-commit must be supplied together",
            file=sys.stderr,
        )
        return 2
    try:
        if args.artifact_manifest:
            validate_contract_finance_manifest(
                args.artifact_manifest,
                expected_producer_commit=args.expected_producer_commit,
            )
        report = build_contract_finance_layer(
            args.input,
            args.out,
            artifact_manifest=args.artifact_manifest,
        )
    except (ContractFinanceLayerError, ContractFinanceManifestGateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
