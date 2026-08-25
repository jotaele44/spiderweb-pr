#!/usr/bin/env python3
"""Execute direct NOAA alternate product paths for Guayama–Punta Tuna."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.marine_alternate_products import (
    fetch_direct,
    parse_nos_product_links,
    parse_stac_item_collection,
)
from pipeline.marine_sources import BoundingBox, freeze_http_response

AOI = BoundingBox(-66.2, 17.5, -65.8, 18.05)
SOURCES = {
    "nos_w00247": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00247.html",
    "dem_2015_6211": "https://coast.noaa.gov/htdata/raster2/elevation/PR_Puerto_Rico_NGS_DEM_2015_6211/stac/noaa_item_collection_m6211.json",
    "dem_2016_8462": "https://coast.noaa.gov/htdata/raster2/elevation/NGS_PR_DEM_2016_8462/stac/noaa_item_collection_m8462.json",
    "dem_2018_8571": "https://coast.noaa.gov/htdata/raster2/elevation/USACE_PR_Topobathy_DEM_2018_8571/stac/noaa_item_collection_m8571.json",
}


def main() -> int:
    out = Path("evidence/marine/guayama_punta_tuna_alternates_v0_3")
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "receipt_version": "0.3",
        "bounded_aoi_wgs84": [AOI.min_lon, AOI.min_lat, AOI.max_lon, AOI.max_lat],
        "sources": {},
        "state": "PASS",
    }
    residues: dict[str, str] = {}
    for key, url in SOURCES.items():
        try:
            frozen = fetch_direct(url)
            body_path, sidecar = freeze_http_response(frozen, out, stem=key)
            if key == "nos_w00247":
                result = parse_nos_product_links(frozen)
                assets = list(result.assets)
                bag_count = sum(1 for item in assets if item.get("kind") == "bag")
                entry = {"asset_count": len(assets), "bag_count": bag_count, "assets": assets}
            else:
                result = parse_stac_item_collection(frozen, AOI)
                assets = list(result.assets)
                entry = {
                    "intersecting_stac_item_count": len(assets),
                    "intersecting_items": assets,
                    "role": "DERIVED_DEM_CONTEXT_NOT_INDEPENDENT_SENSOR",
                }
            entry.update({
                "request_url": frozen.request_url,
                "raw_body": str(body_path),
                "manifest": str(sidecar),
                **frozen.manifest(),
            })
            manifest["sources"][key] = entry
        except Exception as exc:
            residues[key] = f"{type(exc).__name__}: {exc}"
            manifest["sources"][key] = {"request_url": url, "state": "UNRESOLVED", "error": residues[key]}
    if residues:
        manifest["state"] = "PARTIAL_BLOCKED"
    manifest["residue"] = residues
    manifest["certification_boundary"] = (
        "Direct-product discovery only. BAG links remain survey products until bytes and metadata are frozen; "
        "Digital Coast DEM STAC items are derived context and never independent sensor corroboration."
    )
    (out / "alternate_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
