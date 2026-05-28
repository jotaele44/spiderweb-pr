#!/usr/bin/env python3
"""Build the SpiderWeb spatial/operational lane from PR-intake router derivatives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from readiness.spiderweb_spatial_lane import (  # noqa: E402
    SpiderwebSpatialLaneError,
    build_spiderweb_spatial_lane,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True,
                        help="Directory containing spiderweb_pr_derivatives.csv (the router dropzone)")
    parser.add_argument("--out", default=None,
                        help="Output directory for normalized lane artifacts; default: --input")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_spiderweb_spatial_lane(args.input, args.out)
    except SpiderwebSpatialLaneError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["zero_loss_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
