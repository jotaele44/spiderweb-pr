#!/usr/bin/env python3
"""Certify exact SSURGO SurveyArea coverage and MapunitPoly MUKEY denominator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.ssurgo_spatial import certify_exact_spatial_denominator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--surveyarea-raw", type=Path, required=True)
    parser.add_argument("--surveyarea-receipt", type=Path, required=True)
    parser.add_argument("--mapunitpoly-raw", type=Path, required=True)
    parser.add_argument("--mapunitpoly-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(
            f"FAIL: SSURGO exact spatial denominator already exists: "
            f"{args.output}"
        )

    result = certify_exact_spatial_denominator(
        query=json.loads(args.query.read_text(encoding="utf-8")),
        survey_raw_path=args.surveyarea_raw,
        survey_receipt=json.loads(
            args.surveyarea_receipt.read_text(encoding="utf-8")
        ),
        mapunit_raw_path=args.mapunitpoly_raw,
        mapunit_receipt=json.loads(
            args.mapunitpoly_receipt.read_text(encoding="utf-8")
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "state": result["state"],
        "query_id": result["query_id"],
        "survey_coverage_fraction":
            result["survey_coverage"]["coverage_fraction"],
        "retained_polygon_rows":
            result["selection"]["retained_polygon_row_count"],
        "touch_only_rows":
            result["selection"]["touch_only_row_count"],
        "mukey_count": result["selection"]["mukey_count"],
        "canonical_mukey_set_sha256":
            result["selection"]["canonical_mukey_set_sha256"],
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if result["state"] in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
