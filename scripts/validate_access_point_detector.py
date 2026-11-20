#!/usr/bin/env python3
"""Compare the closed-basin detector with a published sinkhole map.

    python scripts/validate_access_point_detector.py --run-id <id>            # rebuild the report
    python scripts/validate_access_point_detector.py --run-id <id> --check    # fail if stale
    python scripts/validate_access_point_detector.py --run-id <id> --extract \\
        --product-dir cache/access_point_products [--lithology FILE]

The default and ``--check`` use only what is committed and touch no network.
``--extract`` also needs the held survey products (and, optionally, the
lithology export) on disk; it re-runs the whole-tile comparison and re-cuts the
committed window.  It touches no network either.

Runs and reference sets are declared in
``configs/access_point_reference_sets.yaml``.  The reference is a published
map, not field truth, and a run changes no registry record.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.access_points import reference, validation  # noqa: E402


def _headline(report: dict) -> dict:
    def table(section: dict) -> dict:
        return {
            "detector_objects": [
                f">= {row['min_depth_m']} m: {row['labels_found']}/{row['labels']} found, "
                f"displaced control {row['displaced_found']}/{row['displaced_labels']}"
                for row in section["object_detection_by_depth_threshold"]
            ],
            "surface": [
                f">= {row['min_depth_m']} m: {row['outlines_on_a_depression']}/"
                f"{row['outlines']} outlines, displaced control "
                f"{row['displaced_on_a_depression']}/{row['displaced_outlines']}"
                for row in section["surface_agreement"]["by_depth_threshold"]
            ],
        }

    out = {
        "run_id": report["run_id"],
        "state": report["window"]["evaluation_state"],
        "window": table(report["window"]),
    }
    for epoch, section in report["whole_tile"]["epochs"].items():
        out[f"whole_tile_{epoch}"] = table(section)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="verify the committed report"
    )
    mode.add_argument("--extract", action="store_true", help="needs the held products")
    parser.add_argument("--product-dir", help="where the held products are")
    parser.add_argument("--lithology", help="the lithology export, checked by hash")
    args = parser.parse_args(argv)

    try:
        run = validation.load_validation_run(
            REPO_ROOT / reference.REFERENCE_PATH, args.run_id
        )
    except validation.ValidationError as exc:
        print(f"VALIDATION RUN NOT USABLE: {exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = validation.check_report(run, repo_root=REPO_ROOT)
        if problems:
            print("VALIDATION REPORT IS STALE:\n  " + "\n  ".join(problems))
            return 1
        print(f"run {args.run_id}: the committed report is reproduced")
        return 0

    if args.extract:
        if not args.product_dir:
            parser.error("--extract needs --product-dir")
        validation.extract(
            run,
            repo_root=REPO_ROOT,
            product_dir=Path(args.product_dir),
            lithology_path=args.lithology,
        )

    report = validation.build_report(run, repo_root=REPO_ROOT)
    validation.write_report(report, repo_root=REPO_ROOT)
    print(json.dumps(_headline(report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
