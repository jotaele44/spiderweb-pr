#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from integration.crim_lookup import CrimLookup, LookupMode


def main() -> int:
    parser = argparse.ArgumentParser(description="CRIM/SIGE parcel lookup")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ident = sub.add_parser("id")
    ident.add_argument(
        "mode",
        choices=[
            LookupMode.NUM_CATASTRO.value,
            LookupMode.OLDPID.value,
            LookupMode.GLOBALID.value,
            LookupMode.OBJECTID.value,
        ],
    )
    ident.add_argument("value")

    point = sub.add_parser("point")
    point.add_argument("lon", type=float)
    point.add_argument("lat", type=float)

    bbox = sub.add_parser("bbox")
    bbox.add_argument("xmin", type=float)
    bbox.add_argument("ymin", type=float)
    bbox.add_argument("xmax", type=float)
    bbox.add_argument("ymax", type=float)

    args = parser.parse_args()
    lookup = CrimLookup()
    if args.cmd == "id":
        result = lookup.identifier(LookupMode(args.mode), args.value)
    elif args.cmd == "point":
        result = lookup.point(args.lon, args.lat)
    else:
        result = lookup.bbox(args.xmin, args.ymin, args.xmax, args.ymax)

    print(
        json.dumps(
            {
                "state": result.state.value,
                "mode": result.mode.value,
                "match_count": result.match_count,
                "identity_state": result.identity_state.value,
                "warnings": result.warnings,
                "candidates": result.candidates,
                "provenance": [item.__dict__ for item in result.provenance],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
