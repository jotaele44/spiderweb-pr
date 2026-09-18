#!/usr/bin/env python3
"""Discovery-only place-name geocoder for Spiderweb LOCATION_QUERY.

Results are candidates, never canonical AOIs. An operator or deterministic
downstream rule must select a result and convert it to point/bbox/GeoJSON before
the LOCATION_QUERY router may use it.
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

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("place")
    parser.add_argument("--output", type=Path, required=True)
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

    candidates = json.loads(raw.decode("utf-8"))
    result = {
        "schema_version": "spiderweb.location_query_geocoder.v1.0",
        "query_raw": args.place,
        "state": "DISCOVERY_ONLY",
        "canonical_aoi": False,
        "provider": "OpenStreetMap Nominatim",
        "request_url": url,
        "http_status": status,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "guardrails": [
            "geocoder result is discovery, not canonical identity",
            "candidate must be converted to bounded geometry before routing",
            "name/proximity alone never certifies place identity",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
