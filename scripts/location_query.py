#!/usr/bin/env python3
"""Plan a canonical Spiderweb LOCATION_QUERY without downloading source bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.location_query import (
    DEFAULT_REGISTRY,
    canonical_json_sha256,
    write_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", type=Path, help="LOCATION_QUERY JSON document")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=Path("outputs/location_query/acquisition_plan.json"))
    args = parser.parse_args()

    query = json.loads(args.query.read_text(encoding="utf-8"))
    plan = write_plan(query, args.out, registry_path=args.registry)
    print(json.dumps({
        "query_id": plan["query"]["query_id"],
        "provider_denominator_count": plan["provider_denominator_count"],
        "route_state_counts": plan["route_state_counts"],
        "request_count": plan["request_count"],
        "provider_registry_sha256": plan["provider_registry_sha256"],
        "plan_sha256": canonical_json_sha256(plan),
        "fetch_gate": plan["fetch_gate"],
        "fetch_blocker_provider_ids": plan["fetch_blocker_provider_ids"],
        "generic_executor_provider_ids": plan["generic_executor_provider_ids"],
        "specialized_adapter_provider_ids": plan["specialized_adapter_provider_ids"],
        "output": str(args.out),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
