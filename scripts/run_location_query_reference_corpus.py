#!/usr/bin/env python3
"""Run the frozen Puerto Rico LOCATION_QUERY reference corpus offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.reference_corpus import run_reference_corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--references",
        type=Path,
        default=Path("configs/location_query_reference_aois.json"),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("configs/location_query_providers.json"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_reference_corpus(
        reference_path=args.references,
        registry_path=args.registry,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "state": result["state"],
        "reference_aoi_count": result["reference_aoi_count"],
        "total_provider_decisions": result["total_provider_decisions"],
        "total_request_specs": result["total_request_specs"],
        "provider_registry_sha256": result["provider_registry_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
