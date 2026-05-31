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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Directory containing Contract-Sweeper adapter outputs")
    parser.add_argument("--out", default=None, help="Output directory for scored layer artifacts; default: --input")
    parser.add_argument(
        "--artifact-manifest",
        default=None,
        help="Optional Contract-Sweeper artifact_manifest.json path. When supplied, the manifest gate must pass before scoring.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_contract_finance_layer(args.input, args.out, artifact_manifest=args.artifact_manifest)
    except ContractFinanceLayerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
