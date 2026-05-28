#!/usr/bin/env python3
"""Fuse Contract-Finance scores into a SpiderWeb airspace/ILAP overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from readiness.contract_finance_fusion import (  # noqa: E402
    ContractFinanceFusionError,
    fuse_contract_finance_scores,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--airspace-overlay", required=True, help="SpiderWeb airspace/ILAP overlay GeoJSON")
    parser.add_argument("--contract-finance-overlay", required=True, help="contract_finance_scored_overlay.geojson")
    parser.add_argument("--out", required=True, help="Output directory for fused overlay/report")
    parser.add_argument("--max-distance-deg", type=float, default=0.045, help="Point proximity threshold in degrees")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = fuse_contract_finance_scores(
            args.airspace_overlay,
            args.contract_finance_overlay,
            args.out,
            max_distance_deg=args.max_distance_deg,
        )
    except ContractFinanceFusionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
