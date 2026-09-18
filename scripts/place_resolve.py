#!/usr/bin/env python3
"""Plan, parse, and explicitly bind discovery-only place geocoding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.place_resolver import (
    bind_candidate_to_location_query,
    build_place_discovery_plan,
    parse_place_candidates,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--query-id", required=True)
    plan.add_argument("--text", required=True)
    plan.add_argument("--limit", type=int, default=10)
    plan.add_argument("--output", type=Path, required=True)

    parse = sub.add_parser("parse")
    parse.add_argument("--raw", type=Path, required=True)
    parse.add_argument("--receipt", type=Path, required=True)
    parse.add_argument("--output", type=Path, required=True)

    bind = sub.add_parser("bind")
    bind.add_argument("--candidates", type=Path, required=True)
    bind.add_argument("--candidate-index", type=int, required=True)
    bind.add_argument("--query-id", required=True)
    bind.add_argument("--point-only", action="store_true")
    bind.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "plan":
        result = build_place_discovery_plan({
            "query_id": args.query_id,
            "text": args.text,
            "limit": args.limit,
            "country_codes": ["pr"],
        })
    elif args.command == "parse":
        result = parse_place_candidates(
            args.raw.read_bytes(),
            json.loads(args.receipt.read_text(encoding="utf-8")),
        )
    else:
        result = bind_candidate_to_location_query(
            candidates=json.loads(args.candidates.read_text(encoding="utf-8")),
            candidate_index=args.candidate_index,
            query_id=args.query_id,
            prefer_bbox=not args.point_only,
        )

    write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
