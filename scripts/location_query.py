#!/usr/bin/env python3
"""Plan a canonical Spiderweb LOCATION_QUERY without downloading source bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.location_query import DEFAULT_REGISTRY, load_registry, route_query


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", type=Path, help="LOCATION_QUERY JSON document")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=Path("outputs/location_query/acquisition_plan.json"))
    args = parser.parse_args()

    query = json.loads(args.query.read_text(encoding="utf-8"))
    plan = route_query(query, registry=load_registry(args.registry))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "query_id": plan["query"]["query_id"],
        "provider_denominator_count": plan["provider_denominator_count"],
        "route_state_counts": plan["route_state_counts"],
        "request_count": plan["request_count"],
        "fetch_gate": plan["fetch_gate"],
        "fetch_blocker_provider_ids": plan["fetch_blocker_provider_ids"],
        "generic_executor_provider_ids": plan["generic_executor_provider_ids"],
        "specialized_adapter_provider_ids": plan["specialized_adapter_provider_ids"],
        "output": str(args.out),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
