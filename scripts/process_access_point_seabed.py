#!/usr/bin/env python3
"""Process a declared seabed-survey run for the Off-Shore Access Point registry.

    python scripts/process_access_point_seabed.py --run-id 2026-11-18-offshore            # rebuild the report
    python scripts/process_access_point_seabed.py --run-id 2026-11-18-offshore --check    # fail if stale
    python scripts/process_access_point_seabed.py --run-id 2026-11-18-offshore --extract \\
        --product-dir cache/access_point_products                                        # needs the held product

The default and ``--check`` use only what is committed: the frozen landing
page, the download manifest, the product facts and the base-grid subset.  They
touch no network.

``--extract`` re-writes the committed subset and product facts from the held
product and therefore needs that file on disk, matching both its download
manifest and the hash the run declares.  It also touches no network: fetching
a product is a separate, explicitly granted step
(``spiderweb.access_points.products``).

Runs are declared under ``seabed_runs`` in
``configs/access_point_survey_runs.yaml``.  A run changes no registry record
and gives no record a position.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.access_points import bathymetry_run  # noqa: E402
from spiderweb.access_points.survey_run import RUNS_PATH  # noqa: E402


def _headline(report: dict) -> dict:
    product = report["products"][0]
    result = product["result"]
    prior = product["prior_receipt"]
    return {
        "run_id": report["run_id"],
        "evaluation_state": report["evaluation_state"],
        "valid_cells": result["surface"]["valid_cells"],
        "elevation_m": [
            result["surface"]["elevation_min_m"],
            result["surface"]["elevation_max_m"],
        ],
        "cell_uncertainty_m": result["surface"]["cell_uncertainty_m"],
        "detections": result["detection_count"],
        "below_uncertainty": result["below_uncertainty"],
        "assertions_by_tier": result["assertions_by_tier"],
        "datum": product["vertical"]["resolved_datum"],
        "datum_plausibility": product["vertical"]["regional_plausibility"],
        "search_area_relation": product["search_area"]["relation"],
        "prior_receipt_agrees": None if prior is None else prior["all_agree"],
        "registry_changes": report["registry_changes"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="verify the committed report"
    )
    mode.add_argument(
        "--extract", action="store_true", help="re-write the subset from the product"
    )
    parser.add_argument(
        "--product-dir", help="where the held product is (with --extract)"
    )
    args = parser.parse_args(argv)

    try:
        run = bathymetry_run.load_run(REPO_ROOT / RUNS_PATH, args.run_id)
    except bathymetry_run.SeabedRunError as exc:
        print(f"SEABED RUN NOT USABLE: {exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = bathymetry_run.check_report(run, repo_root=REPO_ROOT)
        if problems:
            print("SEABED REPORT IS STALE:\n  " + "\n  ".join(problems))
            return 1
        print(
            f"run {args.run_id}: the committed report is reproduced from committed evidence"
        )
        return 0

    if args.extract:
        if not args.product_dir:
            parser.error("--extract needs --product-dir")
        extracted = bathymetry_run.extract(
            run, repo_root=REPO_ROOT, product_dir=Path(args.product_dir)
        )
        print(json.dumps({"subset_sha256": extracted["subset_sha256"]}, indent=2))

    report = bathymetry_run.build_report(run, repo_root=REPO_ROOT)
    bathymetry_run.write_report(report, repo_root=REPO_ROOT)
    print(json.dumps(_headline(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
