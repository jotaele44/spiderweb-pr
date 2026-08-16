#!/usr/bin/env python3
"""Discover direct EX1811 products from NCEI's current cruise landing page."""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from pipeline.marine_alternate_products import fetch_direct
from pipeline.marine_sources import freeze_http_response

LANDING = "https://www.ngdc.noaa.gov/ships/okeanos_explorer/EX1811_mb.html"
PRODUCT_SUFFIXES = (
    ".gsf", ".gsf.gz", ".xyz", ".xyz.gz", ".asc", ".asc.gz",
    ".tif", ".tif.gz", ".tiff", ".tiff.gz", ".kmz", ".kmz.gz",
    ".xml", ".xml.gz", ".tar.gz", ".mb58.gz", ".mb121.gz",
)


def _canonical_noaa_https(target: str) -> str | None:
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc.endswith("noaa.gov"):
        return None
    if parsed.scheme == "http":
        parsed = parsed._replace(scheme="https")
    return urlunparse(parsed)


def main() -> int:
    out = Path("evidence/marine/ex1811_archive_discovery_v0_1")
    out.mkdir(parents=True, exist_ok=True)
    frozen = fetch_direct(LANDING)
    raw, sidecar = freeze_http_response(frozen, out, stem="ex1811_cruise_landing")
    text = frozen.body.decode("utf-8")
    candidates: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I):
        target = _canonical_noaa_https(urljoin(LANDING, unescape(href)))
        if target is None:
            continue
        path = urlparse(target).path.lower()
        if "ex1811" not in path or not path.endswith(PRODUCT_SUFFIXES):
            continue
        if target in seen:
            continue
        seen.add(target)
        candidates.append(target)
    products = [url for url in candidates if "/products/" in urlparse(url).path]
    processed = [url for url in candidates if "/processed/" in urlparse(url).path]
    raw_files = [url for url in candidates if "/raw/" in urlparse(url).path]
    manifest = {
        "receipt_version": "0.3",
        "survey_id": "EX1811",
        "acquisition_root": LANDING,
        "landing_response_sha256": frozen.response_sha256,
        "landing_response_size": frozen.response_size,
        "raw_body": str(raw),
        "manifest": str(sidecar),
        "product_candidate_count": len(candidates),
        "product_candidates": candidates,
        "product_files": products,
        "processed_files": processed,
        "raw_files": raw_files,
        "state": "PASS" if products else "UNRESOLVED",
        "certification_boundary": "Cruise landing discovery only. Legacy HTTP NOAA links are canonicalized to HTTPS; no candidate is evidence until its current URL resolves and bytes/georeferencing are inspected.",
    }
    (out / "archive_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
