#!/usr/bin/env python3
"""Freeze a LOCATION_QUERY provider metadata denominator from preserved bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from spiderweb.provider_denominators import (
    freeze_arcgis_layer_denominator,
    freeze_arcgis_service_denominator,
    freeze_wms_layer_denominator,
)


PARSERS = {
    "arcgis-layers": freeze_arcgis_layer_denominator,
    "arcgis-services": freeze_arcgis_service_denominator,
    "wms-layers": freeze_wms_layer_denominator,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=sorted(PARSERS))
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--request-role", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = args.raw.read_bytes()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    result = PARSERS[args.kind](
        raw=raw,
        receipt=receipt,
        provider_id=args.provider_id,
        request_role=args.request_role,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
