#!/usr/bin/env python3
"""CLI for ingesting Contract-Sweeper v1.1.0 packages into SpiderWeb outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from federation.hub.adapters.contract_sweeper import (  # noqa: E402
    ContractSweeperAdapterError,
    export_contract_sweeper_features,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, help="Contract-Sweeper package directory containing manifest.json")
    parser.add_argument("--out", required=True, help="Output directory for SpiderWeb contract/finance artifacts")
    parser.add_argument(
        "--mode",
        choices=("test", "production"),
        default="test",
        help="Use production to reject synthetic records fail-closed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = export_contract_sweeper_features(args.package, args.out, mode=args.mode)
    except ContractSweeperAdapterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
