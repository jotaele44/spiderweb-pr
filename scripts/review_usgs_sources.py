"""Review frozen source manifestations; exit 2 when scientific staging is blocked."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from federation.usgs_source_review import review_source_manifestations  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("Preserve prior review; choose a new output path")
    report = review_source_manifestations(args.input, args.source_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "assets"}))
    return 0 if report["staging_eligibility"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
