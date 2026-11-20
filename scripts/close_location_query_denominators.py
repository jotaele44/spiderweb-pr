#!/usr/bin/env python3
"""Close provider denominators from an already-preserved discovery fetch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.denominator_closure import close_discovery_denominators


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-receipt", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("configs/location_query_providers.json"))
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    result = close_discovery_denominators(
        fetch=json.loads(args.fetch_receipt.read_text(encoding="utf-8")),
        registry=json.loads(args.registry.read_text(encoding="utf-8")),
        query=json.loads(args.query.read_text(encoding="utf-8")),
        output_dir=args.output_dir,
    )
    receipt = args.output_dir / "LOCATION_QUERY_DENOMINATOR_CLOSURE.json"
    if receipt.exists():
        raise SystemExit(f"FAIL: closure receipt already exists: {receipt}")
    receipt.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
