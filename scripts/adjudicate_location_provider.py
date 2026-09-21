#!/usr/bin/env python3
"""Adjudicate frozen provider layer denominators against provisional registry IDs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.provider_promotion import adjudicate_layer_denominator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("configs/location_query_providers.json"))
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--denominator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    providers = registry.get("providers") or {}
    if args.provider_id not in providers:
        raise SystemExit(f"FAIL: provider not in registry: {args.provider_id}")
    denominator = json.loads(args.denominator.read_text(encoding="utf-8"))
    result = adjudicate_layer_denominator(
        provider_id=args.provider_id,
        provider=providers[args.provider_id],
        denominator=denominator,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
