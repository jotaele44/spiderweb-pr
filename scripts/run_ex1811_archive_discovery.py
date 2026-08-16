#!/usr/bin/env python3
"""Discover direct EX1811 products from NCEI's current cruise landing page."""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from pipeline.marine_alternate_products import fetch_direct
from pipeline.marine_sources import freeze_http_response

LANDING = "https://www.ngdc.noaa.gov/ships/okeanos_explorer/EX1811_mb.html"
PRODUCT_SUFFIXES = (
    ".gsf", ".gsf.gz", ".xyz", ".xyz.gz", ".asc", ".asc.gz",
    ".tif", ".tif.gz", ".tiff", ".tiff.gz", ".kmz", ".kmz.gz",
    ".xml", ".xml.gz", ".tar.gz",
)


def main() -> int:
    out = Path("evidence/marine/ex1811_archive_discovery_v0_1")
    out.mkdir(parents=True, exist_ok=True)
    frozen = fetch_direct(LANDING)
    raw, sidecar = freeze_http_response(frozen, out, stem="ex1811_cruise_landing")
    text = frozen.body.decode("utf-8")
    candidates: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I):
        target = urljoin(LANDING, unescape(href))
        parsed = urlparse(target)
        path = parsed.path.lower()
        if parsed.scheme != "https" or "noaa.gov" not in parsed.netloc:
            continue
        if "ex1811" not in path:
            continue
        if not path.endswith(PRODUCT_SUFFIXES):
            continue
        if target in seen:
            continue
        seen.add(target)
        candidates.append(target)
    manifest = {
        "receipt_version": "0.2",
        "survey_id": "EX1811",
        "acquisition_root": LANDING,
        "landing_response_sha256": frozen.response_sha256,
        "landing_response_size": frozen.response_size,
        "raw_body": str(raw),
        "manifest": str(sidecar),
        "product_candidate_count": len(candidates),
        "product_candidates": candidates,
        "state": "PASS" if candidates else "UNRESOLVED",
        "certification_boundary": "Cruise landing discovery only. Candidate files are not AOI-overlap or depth evidence until bytes/georeferencing are inspected.",
    }
    (out / "archive_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
