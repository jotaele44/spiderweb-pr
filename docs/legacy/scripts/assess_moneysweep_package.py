#!/usr/bin/env python3
"""Run the production readiness gate for a moneysweep-pr export package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from readiness.moneysweep_package_gate import assess_moneysweep_package  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, help="moneysweep-pr export package directory")
    parser.add_argument("--out", default=None, help="Optional report path")
    parser.add_argument("--fail-on-degraded", action="store_true", help="Exit nonzero on DEGRADED as well as NOT_READY")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = assess_moneysweep_package(args.package, args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "NOT_READY":
        return 2
    if args.fail_on_degraded and report["status"] == "DEGRADED":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
