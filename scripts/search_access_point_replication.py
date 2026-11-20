#!/usr/bin/env python3
"""Rebuild or check a declared search for an independent second seabed survey.

    python scripts/search_access_point_replication.py --search-id 2026-11-20-offshore-replication
    python scripts/search_access_point_replication.py --search-id 2026-11-20-offshore-replication --check
    python scripts/search_access_point_replication.py --search-id 2026-11-20-offshore-replication \\
        --extract --product-dir cache/access_point_products       # needs the held candidate

The default and ``--check`` use only what is committed: the frozen footprint
answer and landing pages, the discovery catalogue, the earlier receipts and
the candidate's committed facts.  ``--extract`` reads the held candidate
product once.  Nothing here touches the network or changes a record.

Searches are declared under ``replication_searches`` in
``configs/access_point_survey_runs.yaml``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.access_points import replication  # noqa: E402
from spiderweb.access_points.survey_run import RUNS_PATH  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--search-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="verify the committed report"
    )
    mode.add_argument("--extract", action="store_true", help="read the held candidate")
    parser.add_argument(
        "--product-dir", help="where the held candidate is (with --extract)"
    )
    args = parser.parse_args(argv)
    try:
        search = replication.load_search(REPO_ROOT / RUNS_PATH, args.search_id)
    except replication.ReplicationSearchError as exc:
        print(f"SEARCH NOT USABLE: {exc}", file=sys.stderr)
        return 2
    if args.check:
        problems = replication.check_report(search, repo_root=REPO_ROOT)
        if problems:
            print("REPLICATION SEARCH REPORT IS STALE:\n  " + "\n  ".join(problems))
            return 1
        print(f"search {args.search_id}: the committed report is reproduced")
        return 0
    if args.extract:
        if not args.product_dir:
            parser.error("--extract needs --product-dir")
        replication.extract(
            search, repo_root=REPO_ROOT, product_dir=Path(args.product_dir)
        )
    report = replication.build_report(search, repo_root=REPO_ROOT)
    replication.write_report(report, repo_root=REPO_ROOT)
    print(
        json.dumps(
            {
                "outcome": report["outcome"],
                "cruises": {
                    r["survey_id"]: {
                        "contains": len(r["contains"]),
                        "relation": r["independence"]["relation"],
                        "gridded_at_ncei": r["gridded_product_at_ncei"],
                    }
                    for r in report["cruises"]
                },
                "candidate": (report["candidate_product"] or {}).get("outcome"),
                "prior_reaches": (report["prior_gridded_product"] or {}).get(
                    "reaches_the_depressions"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
