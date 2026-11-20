#!/usr/bin/env python3
"""Build dependent LOCATION_QUERY plans from frozen provider denominators."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.denominator_chain import (
    build_arcgis_layer_aoi_plan,
    build_usace_service_metadata_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    usace = sub.add_parser("usace-services")
    usace.add_argument("--query", type=Path, required=True)
    usace.add_argument("--denominator", type=Path, required=True)
    usace.add_argument("--service-root", required=True)
    usace.add_argument("--output", type=Path, required=True)

    layers = sub.add_parser("arcgis-layers")
    layers.add_argument("--query", type=Path, required=True)
    layers.add_argument("--denominator", type=Path, required=True)
    layers.add_argument("--provider-id", required=True)
    layers.add_argument("--service-url", required=True)
    layers.add_argument("--role-prefix", default="layer")
    layers.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    query = json.loads(args.query.read_text(encoding="utf-8"))
    denominator = json.loads(args.denominator.read_text(encoding="utf-8"))

    if args.command == "usace-services":
        result = build_usace_service_metadata_plan(
            query=query,
            service_root=args.service_root,
            denominator=denominator,
        )
    else:
        result = build_arcgis_layer_aoi_plan(
            query=query,
            provider_id=args.provider_id,
            service_url=args.service_url,
            denominator=denominator,
            role_prefix=args.role_prefix,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
