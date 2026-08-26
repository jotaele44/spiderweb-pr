#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from integration.crim_lookup import (
    CrimError,
    CrimLookup,
    IdentityState,
    InvalidInputError,
    LookupMode,
    LookupResult,
    LookupState,
    PaginationError,
    SchemaDriftError,
    SourceResponseError,
    SourceTransportError,
)


def _result_payload(result: LookupResult) -> dict[str, Any]:
    return {
        "state": result.state.value,
        "mode": result.mode.value,
        "match_count": result.match_count,
        "identity_state": result.identity_state.value,
        "warnings": result.warnings,
        "candidates": result.candidates,
        "provenance": [item.__dict__ for item in result.provenance],
    }


def _error_state(error: CrimError) -> LookupState:
    if isinstance(error, InvalidInputError):
        return LookupState.INVALID_INPUT
    if isinstance(error, SchemaDriftError):
        return LookupState.SCHEMA_DRIFT
    if isinstance(error, PaginationError):
        return LookupState.TRUNCATED
    if isinstance(error, (SourceTransportError, SourceResponseError)):
        return LookupState.SOURCE_ERROR
    return LookupState.UNRESOLVED


def main(argv: list[str] | None = None, *, lookup: CrimLookup | None = None) -> int:
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
    point.add_argument("lon")
    point.add_argument("lat")

    bbox = sub.add_parser("bbox")
    bbox.add_argument("xmin")
    bbox.add_argument("ymin")
    bbox.add_argument("xmax")
    bbox.add_argument("ymax")

    args = parser.parse_args(argv)
    lookup = lookup or CrimLookup()
    if args.cmd == "id":
        mode = LookupMode(args.mode)
    elif args.cmd == "point":
        mode = LookupMode.POINT
    else:
        mode = LookupMode.BBOX

    try:
        if args.cmd == "id":
            result = lookup.identifier(mode, args.value)
        elif args.cmd == "point":
            result = lookup.point(args.lon, args.lat)
        else:
            result = lookup.bbox(args.xmin, args.ymin, args.xmax, args.ymax)
    except CrimError as exc:
        payload = {
            "state": _error_state(exc).value,
            "mode": mode.value,
            "match_count": 0,
            "identity_state": IdentityState.UNRESOLVED.value,
            "warnings": [str(exc)],
            "candidates": [],
            "provenance": [],
            "error_type": type(exc).__name__,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(_result_payload(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
