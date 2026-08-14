#!/usr/bin/env python3
"""Fail-closed runtime checks for the Spiderweb Martin municipios canary.

This script does not certify semantic parity by itself. It verifies that a
running Martin instance exposes exactly the named canary source and that its
TileJSON contract is coherent with Spiderweb's frozen delivery registry.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DELIVERY = ROOT / "configs" / "martin_delivery.yaml"


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    delivery = yaml.safe_load(DELIVERY.read_text(encoding="utf-8")) or {}
    expected = delivery["sources"]
    expected_ids = set(expected)

    try:
        catalog = get_json(f"{base}/catalog")
        tiles = catalog.get("tiles", catalog)
        actual_ids = set(tiles)
        if actual_ids != expected_ids:
            raise RuntimeError(
                "Martin catalog mismatch: "
                f"expected={sorted(expected_ids)} actual={sorted(actual_ids)}"
            )

        for layer_id, spec in expected.items():
            tj = get_json(f"{base}{spec['tilejson_path']}")
            vector_layers = tj.get("vector_layers") or []
            advertised = {x.get("id") for x in vector_layers}
            if spec["source_layer"] not in advertised:
                raise RuntimeError(
                    f"{layer_id}: TileJSON vector_layers={sorted(advertised)} "
                    f"does not advertise {spec['source_layer']!r}"
                )
            tiles_urls = tj.get("tiles") or []
            if not tiles_urls:
                raise RuntimeError(f"{layer_id}: TileJSON has no tile URLs")

        print("PASS: Martin canary catalog is explicit and exact")
        print(f"PASS: sources={','.join(sorted(actual_ids))}")
        return 0
    except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
