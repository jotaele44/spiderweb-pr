#!/usr/bin/env python3
"""Re-query derived NOAA DEM STAC collections against the selected W00247 BAG extent."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.marine_alternate_products import fetch_direct, parse_stac_item_collection
from pipeline.marine_sources import BoundingBox, freeze_http_response

BAG = BoundingBox(-65.9833772516194, 17.723098751773474, -65.82659038887648, 17.873293497881694)
SOURCES = {
    "6211_2015_ngs": "https://coast.noaa.gov/htdata/raster2/elevation/PR_Puerto_Rico_NGS_DEM_2015_6211/stac/noaa_item_collection_m6211.json",
    "8462_2016_ngs": "https://coast.noaa.gov/htdata/raster2/elevation/NGS_PR_DEM_2016_8462/stac/noaa_item_collection_m8462.json",
    "8571_2018_usace_fema": "https://coast.noaa.gov/htdata/raster2/elevation/USACE_PR_Topobathy_DEM_2018_8571/stac/noaa_item_collection_m8571.json",
}


def main() -> int:
    out = Path("evidence/marine/w00247_context_overlap_v0_1")
    out.mkdir(parents=True, exist_ok=True)
    sources: dict[str, object] = {}
    for key, url in SOURCES.items():
        frozen = fetch_direct(url)
        body, sidecar = freeze_http_response(frozen, out, stem=key)
        selected = parse_stac_item_collection(frozen, BAG)
        sources[key] = {
            "request_url": url,
            "response_sha256": frozen.response_sha256,
            "response_size": frozen.response_size,
            "raw_body": str(body),
            "manifest": str(sidecar),
            "intersecting_item_count": len(selected.assets),
            "role": "DERIVED_DEM_CONTEXT_NOT_INDEPENDENT_SENSOR",
        }
    counts = {key: int(value["intersecting_item_count"]) for key, value in sources.items()}
    manifest = {
        "receipt_version": "0.1",
        "selected_w00247_bag_bbox_wgs84": [BAG.min_lon, BAG.min_lat, BAG.max_lon, BAG.max_lat],
        "sources": sources,
        "intersection_counts": counts,
        "state": "PASS" if all(value == 0 for value in counts.values()) else "OVERLAP_PRESENT",
        "binding": (
            "Zero STAC tile intersections means these three derived DEM families cannot spatially crossvalidate "
            "the selected W00247 BAG tile. It does not mean they lack coverage elsewhere in the broader corridor."
        ),
    }
    (out / "overlap_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
