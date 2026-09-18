#!/usr/bin/env python3
"""Merge frozen ArcGIS service denominators while preserving folder scope."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.provider_denominators import (
    merge_arcgis_service_denominators,
    merge_arcgis_service_contents_denominators,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["services", "contents"])
    parser.add_argument("denominators", nargs="+", type=Path)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.denominators
    ]
    merger = (
        merge_arcgis_service_denominators
        if args.kind == "services"
        else merge_arcgis_service_contents_denominators
    )
    result = merger(rows, provider_id=args.provider_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
