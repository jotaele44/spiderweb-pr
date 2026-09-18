#!/usr/bin/env python3
"""Discovery-only place-name geocoder for Spiderweb LOCATION_QUERY.

Results are candidates, never canonical AOIs. Raw provider bytes are frozen
before JSON interpretation. An operator or independently justified downstream
rule must select a candidate and convert it to point/bbox/GeoJSON before the
LOCATION_QUERY router may use it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "spiderweb-pr-location-query-geocoder/1.0"
PR_VIEWBOX = "-67.4,18.6,-65.2,17.8"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("place")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    params = {
        "q": args.place,
        "format": "jsonv2",
        "limit": max(1, min(args.limit, 20)),
        "bounded": 1,
        "viewbox": PR_VIEWBOX,
        "addressdetails": 1,
    }
    url = ENDPOINT + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=60) as response:  # noqa: S310
        raw = response.read()
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")

    raw_path = args.raw_output or args.output.with_suffix(args.output.suffix + ".raw")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    frozen_sha = sha256_bytes(raw)

    candidates = json.loads(raw.decode("utf-8"))
    if not isinstance(candidates, list):
        raise SystemExit("FAIL: geocoder response is not a candidate list")

    result = {
        "schema_version": "spiderweb.location_query_geocoder.v1.1",
        "query_raw": args.place,
        "state": "DISCOVERY_ONLY",
        "canonical_aoi": False,
        "provider": "OpenStreetMap Nominatim",
        "request_url": url,
        "http_status": status,
        "content_type": content_type,
        "raw_path": str(raw_path),
        "raw_bytes": len(raw),
        "raw_sha256": frozen_sha,
        "raw_bytes_preserved_before_interpretation": True,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "guardrails": [
            "geocoder result is discovery, not canonical identity",
            "candidate must be converted to bounded geometry before routing",
            "name/proximity alone never certifies place identity",
            "raw provider bytes are preserved before candidate interpretation",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
