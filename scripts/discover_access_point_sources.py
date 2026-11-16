#!/usr/bin/env python3
"""Plan, run or re-check a metadata-only source discovery for the access-point registries.

With no option this prints the plan and touches nothing: no network, no file.

    python scripts/discover_access_point_sources.py                  # plan only
    python scripts/discover_access_point_sources.py --execute \\
        --run-id 2026-11-16                                          # live run
    python scripts/discover_access_point_sources.py --verify 2026-11-16

A live run needs an explicit grant in the environment, and the grant bounds it:

    SPIDERWEB_ACCESS_POINT_ACQUISITION=metadata:<requests per target>:<who granted it>

It asks public catalogues which surveys they list for each search box and keeps
the exact answers.  It downloads no data product, changes no feature, and gives
no off-shore seed a position.  ``--verify`` replays the kept bytes offline and
fails if they no longer reproduce the committed receipts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.access_points import acquisition as acq  # noqa: E402
from spiderweb.access_points import discovery  # noqa: E402
from spiderweb.access_points.namespaces import Namespace  # noqa: E402
from spiderweb.access_points.registry import AccessPointRegistry  # noqa: E402
from spiderweb.access_points.seeding import (  # noqa: E402
    GUAYAMA_RECEIPT_PATH,
    REGISTRY_DIR,
)

GUAYAMA_TARGET = "guayama_punta_tuna_discovery_v0_1"


def _registries() -> list[AccessPointRegistry]:
    return [
        AccessPointRegistry.load(REPO_ROOT / REGISTRY_DIR / name)
        for name in ("inland.json", "offshore.json")
    ]


def _guayama_comparison(run: discovery.DiscoveryRun) -> dict[str, object] | None:
    """Set comparison with the August receipt, which asked about the same box."""

    if not any(r.target.target_id == GUAYAMA_TARGET for r in run.results):
        return None
    receipt = json.loads((REPO_ROOT / GUAYAMA_RECEIPT_PATH).read_text(encoding="utf-8"))
    listed = {
        "NCEI_MULTIBEAM_CATALOG": [
            f"NCEI:multibeam:{s}" for s in receipt["ncei_multibeam_survey_ids"]
        ],
        "NCEI_SOUNDING_CATALOG": [
            f"NCEI:sounding:{s}" for s in receipt["ncei_sounding_survey_ids"]
        ],
        "NOS_BAG_INVENTORY": [f"NOS:BAG:{s}" for s in receipt["nos_bag_survey_ids"]],
        "USIEI_TOPOBATHY_LIDAR": [
            f"USIEI:GlobalID:{f['globalid']}"
            for f in receipt["usiei_topobathy_features"]
        ],
        "USIEI_BATHYMETRIC_LIDAR": [],
        "USIEI_OTHER_BATHYMETRIC": [],
    }
    comparison = discovery.compare_with_listing(
        run,
        target_id=GUAYAMA_TARGET,
        bbox=receipt["source"]["bounded_aoi_wgs84"],
        listed=listed,
    )
    comparison["earlier_record"] = GUAYAMA_RECEIPT_PATH
    comparison["note"] = (
        "identifier sets for the same box at two dates; a difference is a change in "
        "what the catalogue lists, not a change at sea"
    )
    return comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute", action="store_true", help="make live metadata requests"
    )
    mode.add_argument(
        "--verify", metavar="RUN_ID", help="replay a kept run offline and compare"
    )
    parser.add_argument("--run-id", help="directory name for a live run (a date)")
    parser.add_argument("--max-total-requests", type=int, default=150)
    parser.add_argument("--min-interval-s", type=float, default=1.0)
    parser.add_argument("--user-agent", default=acq.GENERIC_USER_AGENT)
    parser.add_argument(
        "--no-raw", action="store_true", help="do not keep the exact response bytes"
    )
    args = parser.parse_args(argv)

    root = REPO_ROOT / discovery.DISCOVERY_DIR
    if args.verify:
        problems = discovery.verify_run(root / args.verify)
        if problems:
            print("DISCOVERY EVIDENCE DOES NOT REPRODUCE:\n  " + "\n  ".join(problems))
            return 1
        print(
            f"run {args.verify}: kept bytes reproduce every receipt and the catalogue"
        )
        return 0

    registries = _registries()
    config = discovery.load_corridor_config(REPO_ROOT / discovery.CORRIDORS_PATH)
    targets = discovery.build_targets(config, registries)

    if not args.execute:
        print(json.dumps(discovery.plan(targets), indent=2, sort_keys=True))
        return 0

    if not args.run_id:
        parser.error("--execute needs --run-id")
    authorization = acq.Authorization.from_environment()
    if authorization.level is not acq.AuthorizationLevel.METADATA_DISCOVERY:
        print(
            f"NOT AUTHORISED: set {acq.AUTHORIZATION_ENV}=metadata:<n>:<who>. "
            "Nothing was requested.",
            file=sys.stderr,
        )
        return 2

    transport = acq.with_rate_limit(
        acq.with_retry(acq.live_transport(user_agent=args.user_agent)),
        min_interval_s=args.min_interval_s,
    )
    run = discovery.run_discovery(
        targets,
        run_id=args.run_id,
        discovered_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        transport=transport,
        authorization=authorization,
        max_total_requests=args.max_total_requests,
    )
    points = {
        registry.namespace: discovery.registered_points(registry)
        for registry in registries
    }
    catalogue = discovery.write_run(
        run, root, feature_points=points, keep_raw=not args.no_raw
    )
    comparison = _guayama_comparison(run)
    if comparison is not None:
        (root / args.run_id / "comparison_with_guayama_receipt.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(catalogue["totals"], indent=2, sort_keys=True))
    for entry in catalogue["targets"]:
        states = ", ".join(
            f"{p['provider_id']}={p['state']}:{p['row_count']}"
            for p in entry["providers"]
        )
        print(f"{entry['target_id']} [{entry['state']}] {states}")
    inland = catalogue["totals"]["sources_by_namespace"].get(
        Namespace.ACCESS_POINT_INLAND.value, 0
    )
    print(f"run state: {catalogue['state']}; inland sources: {inland}")
    return 0 if catalogue["state"] in {"PASS", "ZERO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
