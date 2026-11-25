"""CLI for the DEM platform catalog.

``summary`` prints the breakdown by acquisition platform and the registration
accounting; it exits 1 if any registration is unaccounted for or any catalog
reference is stale. ``check --sources a,b`` prints the merge policy and the
pairwise independence of the selected products as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys

from .catalog import account, group_by_platform_class, load_catalog, products_by_id
from .policy import evaluate_platform_mix, pairwise_independence


def summary(_: argparse.Namespace) -> int:
    catalog = load_catalog()
    for cls, products in group_by_platform_class(catalog).items():
        print(f"{cls} ({len(products)})")
        for p in products:
            status = "" if p["platform_status"] == "verified" else "  [unverified]"
            print(f"  {p['source_id']:42s} {p['surface_model']:24s} {p['vertical_datum']}{status}")
    acc = account(catalog).as_dict()
    print(
        f"\nregistrations: {acc['registrations']} in {acc['files']} files; "
        f"{acc['aliases']} aliases of {len(catalog['products'])} products, "
        f"{acc['non_product_registrations']} non-product; accounted {acc['accounted_percent']}%"
    )
    problems = acc["unaccounted"] + acc["stale"] + acc["double_counted"]
    for label in ("unaccounted", "stale", "double_counted"):
        for reg in acc[label]:
            print(f"  {label}: {reg['path']} :: {reg['id']}", file=sys.stderr)
    print(f"open registry conflicts: {sum(1 for c in catalog['registry_conflicts'] if c['status'] == 'open')}")
    return 1 if problems else 0


def check(args: argparse.Namespace) -> int:
    products = products_by_id(load_catalog())
    ids = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [i for i in ids if i not in products]
    if unknown:
        print(f"unknown source_id: {', '.join(unknown)}", file=sys.stderr)
        return 2
    selected = [products[i] for i in ids]
    print(json.dumps({"policy": evaluate_platform_mix(selected).as_dict(), "independence": pairwise_independence(selected)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m source_adapters.dem_platform.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary").set_defaults(func=summary)
    p_check = sub.add_parser("check")
    p_check.add_argument("--sources", required=True, help="comma-separated catalog source_ids")
    p_check.set_defaults(func=check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
