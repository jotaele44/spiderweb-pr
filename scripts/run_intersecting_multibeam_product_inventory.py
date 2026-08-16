#!/usr/bin/env python3
"""Inventory direct NOAA/NCEI processed products for W00247-intersecting multibeam roots."""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from pipeline.marine_alternate_products import fetch_direct
from pipeline.marine_sources import freeze_http_response

FOOTPRINT_MANIFEST = Path("evidence/marine/w00247_multibeam_footprints_v0_1/footprint_manifest.json")
OUT = Path("evidence/marine/w00247_multibeam_product_inventory_v0_1")
PRODUCT_SUFFIXES = (
    ".xyz", ".xyz.gz", ".asc", ".asc.gz", ".tif", ".tif.gz", ".tiff", ".tiff.gz",
    ".bag", ".bag.gz", ".gsf", ".gsf.gz", ".grd", ".grd.gz", ".nc", ".nc.gz",
    ".kmz", ".kml", ".xml", ".xml.gz", ".tar.gz", ".zip",
)


def _canonical_https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.netloc.endswith("noaa.gov"):
        return parsed._replace(scheme="https").geturl()
    return url


def _probe(url: str) -> dict[str, object]:
    req = Request(url, method="HEAD", headers={"User-Agent": "spiderweb-pr/0.1 marine-evidence"})
    try:
        with urlopen(req, timeout=30) as response:
            return {
                "status": int(getattr(response, "status", 200)),
                "content_length": int(response.headers["Content-Length"]) if response.headers.get("Content-Length", "").isdigit() else None,
                "content_type": response.headers.get("Content-Type"),
                "final_url": response.geturl(),
            }
    except Exception as exc:
        return {"status": None, "content_length": None, "content_type": None, "final_url": None, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    footprint = json.loads(FOOTPRINT_MANIFEST.read_text(encoding="utf-8"))
    unique: dict[str, dict[str, object]] = {}
    for row in footprint["frozen_denominator_intersections"]:
        attrs = row.get("attributes", {})
        survey_id = str(attrs.get("SURVEY_ID") or "").strip()
        download_url = str(attrs.get("DOWNLOAD_URL") or "").strip()
        if survey_id and download_url and survey_id not in unique:
            unique[survey_id] = {
                "survey_id": survey_id,
                "ncei_id": attrs.get("NCEI_ID"),
                "survey_year": attrs.get("SURVEY_YEAR"),
                "instrument": attrs.get("INSTRUMENT"),
                "landing_url": _canonical_https(download_url),
            }

    OUT.mkdir(parents=True, exist_ok=True)
    surveys: list[dict[str, object]] = []
    for survey_id in sorted(unique):
        meta = unique[survey_id]
        landing_url = str(meta["landing_url"])
        try:
            frozen = fetch_direct(landing_url)
        except Exception as exc:
            surveys.append({**meta, "state": "BLOCKED", "error": f"{type(exc).__name__}: {exc}", "product_candidates": []})
            continue
        raw, sidecar = freeze_http_response(frozen, OUT, stem=f"{survey_id}_landing")
        text = frozen.body.decode("utf-8", errors="replace")
        seen: set[str] = set()
        candidates: list[dict[str, object]] = []
        for href in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I):
            target = _canonical_https(urljoin(landing_url, unescape(href)))
            parsed = urlparse(target)
            if parsed.scheme != "https" or not parsed.netloc.endswith("noaa.gov"):
                continue
            if not parsed.path.lower().endswith(PRODUCT_SUFFIXES):
                continue
            if target in seen:
                continue
            seen.add(target)
            candidates.append({"url": target, **_probe(target)})
        surveys.append({
            **meta,
            "state": "PASS" if candidates else "UNRESOLVED",
            "landing_response_sha256": frozen.response_sha256,
            "landing_response_size": frozen.response_size,
            "landing_raw_body": str(raw),
            "landing_manifest": str(sidecar),
            "product_candidate_count": len(candidates),
            "product_candidates": candidates,
        })

    manifest = {
        "receipt_version": "0.1",
        "source_footprint_response_sha256": footprint["response_sha256"],
        "unique_intersecting_frozen_surveys": len(unique),
        "surveys": surveys,
        "state": "PASS" if surveys and all(row["state"] == "PASS" for row in surveys) else "PARTIAL",
        "certification_boundary": "Landing-page product inventory and byte-size probing only. Product URLs are not depth evidence until exact bytes are downloaded, hashed, parsed, and shown to contain nonzero observations inside the W00247 BAG extent.",
    }
    (OUT / "product_inventory_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
