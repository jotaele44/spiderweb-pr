#!/usr/bin/env python3
"""Process a declared real-survey run for the access-point registries.

    python scripts/process_access_point_survey.py --run-id 2026-11-17            # rebuild the report
    python scripts/process_access_point_survey.py --run-id 2026-11-17 --check    # fail if stale
    python scripts/process_access_point_survey.py --run-id 2026-11-17 --extract \\
        --product-dir cache/access_point_products                               # needs the held products

The default and ``--check`` use only what is committed: the frozen catalogue
answer, the download manifests and the window subsets.  They touch no network.

``--extract`` re-cuts the committed window subsets from the held products and
therefore needs those products on disk, each matching its download manifest.
It also touches no network: fetching a product is a separate, explicitly
granted step (``spiderweb.access_points.products``).

Runs are declared in ``configs/access_point_survey_runs.yaml``.  A run changes
no registry record.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.access_points import survey_run  # noqa: E402


def _headline(report: dict) -> dict:
    out: dict = {"run_id": report["run_id"], "target": report["target_feature"]}
    for product in report["products"]:
        result = product["result"]
        out[product["epoch"]] = {
            "detections": result["detection_count"],
            "deepest_m": max(
                (d["max_depth_m"] for d in result["detections"]), default=None
            ),
            "assertions_by_tier": result["assertions_by_tier"],
            "datum": product["vertical"]["resolved_datum"],
            "datum_plausibility": product["vertical"]["regional_plausibility"],
        }
    if report["replication"]:
        out["replicated"] = (
            f"{report['replication']['replicated']} of "
            f"{report['replication']['earlier_detections']}"
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="verify the committed report"
    )
    mode.add_argument(
        "--extract", action="store_true", help="re-cut subsets from held products"
    )
    parser.add_argument(
        "--product-dir", help="where the held products are (with --extract)"
    )
    args = parser.parse_args(argv)

    try:
        run = survey_run.load_run(REPO_ROOT / survey_run.RUNS_PATH, args.run_id)
    except survey_run.SurveyRunError as exc:
        print(f"SURVEY RUN NOT USABLE: {exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = survey_run.check_report(run, repo_root=REPO_ROOT)
        if problems:
            print("SURVEY REPORT IS STALE:\n  " + "\n  ".join(problems))
            return 1
        print(
            f"run {args.run_id}: the committed report is reproduced from committed evidence"
        )
        return 0

    if args.extract:
        if not args.product_dir:
            parser.error("--extract needs --product-dir")
        extracted = survey_run.extract(
            run, repo_root=REPO_ROOT, product_dir=Path(args.product_dir)
        )
        print(json.dumps(extracted["subsets"], indent=2, sort_keys=True))

    report = survey_run.build_report(run, repo_root=REPO_ROOT)
    survey_run.write_report(report, repo_root=REPO_ROOT)
    print(json.dumps(_headline(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
