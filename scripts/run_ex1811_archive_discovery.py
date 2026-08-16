#!/usr/bin/env python3
"""Discover direct EX1811 multibeam archive products without using failing NEXT /file APIs."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from pipeline.marine_archive_sources import fetch_archive_listing, product_candidates
from pipeline.marine_sources import freeze_http_response

ROOT = "https://data.ngdc.noaa.gov/platforms/ocean/ships/noaa_ship_okeanos_explorer_(r337)/EX1811/multibeam/data/version1/MB/"
MAX_DEPTH = 3


def main() -> int:
    out = Path("evidence/marine/ex1811_archive_discovery_v0_1")
    out.mkdir(parents=True, exist_ok=True)
    queue: list[tuple[str, int]] = [(ROOT, 0)]
    visited: set[str] = set()
    candidates: set[str] = set()
    listings: list[dict[str, object]] = []
    while queue:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            listing = fetch_archive_listing(url)
        except Exception as exc:
            listings.append({"url": url, "depth": depth, "state": "UNRESOLVED", "error": f"{type(exc).__name__}: {exc}"})
            continue
        stem = f"listing_{len(listings):04d}"
        raw, sidecar = freeze_http_response(listing.frozen, out, stem=stem)
        local_candidates = product_candidates(listing.links)
        candidates.update(local_candidates)
        listings.append({
            "url": url,
            "depth": depth,
            "state": "PASS",
            "raw_body": str(raw),
            "manifest": str(sidecar),
            "link_count": len(listing.links),
            "product_candidate_count": len(local_candidates),
        })
        if depth >= MAX_DEPTH:
            continue
        for target in listing.links:
            path = urlparse(target).path
            if target.endswith("/") and path.startswith(urlparse(ROOT).path):
                queue.append((target, depth + 1))
    manifest = {
        "receipt_version": "0.1",
        "survey_id": "EX1811",
        "acquisition_root": ROOT,
        "max_depth": MAX_DEPTH,
        "listing_count": len(listings),
        "product_candidate_count": len(candidates),
        "product_candidates": sorted(candidates),
        "listings": listings,
        "state": "PASS" if all(row["state"] == "PASS" for row in listings) else "PARTIAL_BLOCKED",
        "certification_boundary": "Direct archive discovery only. Candidate files are not AOI-overlap or depth evidence until their bytes/georeferencing are inspected.",
    }
    (out / "archive_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
