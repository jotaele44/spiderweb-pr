#!/usr/bin/env python3
"""Build a provisional site imagery timeline document from an offline fixture.

Reads a frozen site list and a synthetic scenes fixture, runs the timeline over them
and prints a summary. **Nothing is written unless ``--out`` is given**, and an
existing file is never replaced without ``--overwrite``.

Without ``--scenes-fixture`` the live acquisition adapter is used, which is a
fail-closed stub: live Sentinel-2 acquisition needs credentials supplied through
environment variables and is interim pending the hub acquisition runtime (hub ADR
0006). It fetches nothing and exits 3.

Exit codes: 0 ok, 2 invalid input or document, 3 acquisition unavailable, 4 change
metric unavailable.

The output document feeds ``scripts/federation_export.py --site-imagery-timeline``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spiderweb.site_timeline.adapters import (  # noqa: E402
    AcquisitionAdapter,
    AcquisitionUnavailable,
    SyntheticAdapter,
    UnavailableAdapter,
)
from spiderweb.site_timeline.fixtures import (  # noqa: E402
    load_scenes,
    load_sites,
)
from spiderweb.site_timeline.metrics import (  # noqa: E402
    ChangeMetric,
    MetricUnavailable,
    PixelDifferenceMetric,
)
from spiderweb.site_timeline.series import DEFAULT_CLOUD_CUTOFF_PCT  # noqa: E402
from spiderweb.site_timeline.timeline import (  # noqa: E402
    build_document,
    build_site_timeline,
    to_json,
    validate_document,
)

# Sentinel-2A launch date: no Sentinel-2 scene can predate it.
DEFAULT_START = "2015-06-23"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _summary(document: dict[str, Any], wrote: str | None) -> dict[str, Any]:
    return {
        "schema_version": document["schema_version"],
        "synthetic": document["synthetic"],
        "provisional": document["provisional"],
        "adapter": document["adapter"],
        "wrote": wrote,
        "sites": [
            {
                "external_site_id": s["site"]["external_site_id"],
                "ledger": s["ledger"],
                "comparisons": [
                    {
                        "pair_kind": c["pair_kind"],
                        "epoch_class": c["epoch_class"],
                        "disposition": c["disposition"],
                        "classification": (c["signal"]["result"]["score"] or {}).get(
                            "classification"
                        ),
                    }
                    for c in s["comparisons"]
                ],
            }
            for s in document["sites"]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site-list", required=True, help="frozen site list (JSON)")
    ap.add_argument(
        "--scenes-fixture",
        default=None,
        help="synthetic scenes and change signals (JSON); omit for the live stub",
    )
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=None, help="default: today (UTC)")
    ap.add_argument(
        "--cloud-cutoff",
        type=float,
        default=DEFAULT_CLOUD_CUTOFF_PCT,
        help="exclude scenes above this cloud cover %% (uncalibrated heuristic)",
    )
    ap.add_argument("--now", default=None, help="timestamp to stamp records with")
    ap.add_argument("--out", default=None, help="write the document here (opt-in)")
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="allow --out to replace an existing file",
    )
    ap.add_argument(
        "--print",
        dest="print_document",
        action="store_true",
        help="print the whole document instead of the summary",
    )
    args = ap.parse_args(argv)

    now = args.now or _utc_now()
    end = args.end or now[:10]

    try:
        sites = load_sites(json.loads(Path(args.site_list).read_text()))
        adapter: AcquisitionAdapter
        metric: ChangeMetric
        if args.scenes_fixture:
            scenes, metric = load_scenes(
                sites, json.loads(Path(args.scenes_fixture).read_text())
            )
            adapter = SyntheticAdapter(scenes)
        else:
            adapter, metric = UnavailableAdapter(), PixelDifferenceMetric()
    except (OSError, ValueError) as exc:  # FixtureError is a ValueError
        print(f"FAIL — input rejected: {exc}", file=sys.stderr)
        return 2

    try:
        timelines = [
            build_site_timeline(
                site,
                adapter,
                metric,
                start=args.start,
                end=end,
                now=now,
                cloud_cutoff_pct=args.cloud_cutoff,
            )
            for site in sites
        ]
    except AcquisitionUnavailable as exc:
        print(f"FAIL — acquisition unavailable: {exc}", file=sys.stderr)
        return 3
    except MetricUnavailable as exc:
        print(f"FAIL — change metric unavailable: {exc}", file=sys.stderr)
        return 4

    document = build_document(
        timelines, now=now, adapter_name=adapter.name, start=args.start, end=end
    )
    problems = validate_document(document)
    if problems:
        print(f"FAIL — document invalid ({len(problems)} problems):", file=sys.stderr)
        for problem in problems[:20]:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    wrote = None
    if args.out:
        target = Path(args.out)
        if target.exists() and not args.overwrite:
            print(
                f"FAIL — {target} exists; pass --overwrite to replace it",
                file=sys.stderr,
            )
            return 2
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(to_json(document))
        wrote = str(target)

    print(
        to_json(document)
        if args.print_document
        else json.dumps(_summary(document, wrote), indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
