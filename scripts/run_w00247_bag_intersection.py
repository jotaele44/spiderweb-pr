#!/usr/bin/env python3
"""Download W00247 BAG products, hash bytes, and intersect their raster bounds with the AOI."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import rasterio
from rasterio.warp import transform_bounds

from pipeline.marine_alternate_products import fetch_direct, parse_nos_product_links
from pipeline.marine_sources import BoundingBox, freeze_http_response

AOI = BoundingBox(-66.2, 17.5, -65.8, 18.05)
LANDING = "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00247.html"


def _relation(bounds: tuple[float, float, float, float]) -> str:
    x1, y1, x2, y2 = bounds
    if x2 < AOI.min_lon or x1 > AOI.max_lon or y2 < AOI.min_lat or y1 > AOI.max_lat:
        return "OUTSIDE"
    if x1 >= AOI.min_lon and x2 <= AOI.max_lon and y1 >= AOI.min_lat and y2 <= AOI.max_lat:
        return "FULLY_WITHIN"
    if x2 == AOI.min_lon or x1 == AOI.max_lon or y2 == AOI.min_lat or y1 == AOI.max_lat:
        return "TOUCH_ONLY"
    return "PARTIAL"


def _download(url: str, path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    req = Request(url, headers={"User-Agent": "spiderweb-pr/0.1 marine-evidence"})
    with urlopen(req, timeout=120) as response, path.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def main() -> int:
    out = Path("evidence/marine/w00247_bag_v0_1")
    raw = out / "raw"
    selected_dir = out / "selected"
    raw.mkdir(parents=True, exist_ok=True)
    selected_dir.mkdir(parents=True, exist_ok=True)

    landing = fetch_direct(LANDING)
    freeze_http_response(landing, out, stem="w00247_landing")
    products = parse_nos_product_links(landing)
    bag_urls = [str(item["url"]) for item in products.assets if item.get("kind") == "bag"]
    if len(bag_urls) != 4:
        raise ValueError(f"expected exactly 4 BAG links from W00247 landing page, got {len(bag_urls)}")

    rows: list[dict[str, object]] = []
    for url in bag_urls:
        name = url.rsplit("/", 1)[-1]
        path = raw / name
        sha256, size = _download(url, path)
        with rasterio.open(path) as ds:
            if ds.crs is None:
                wgs84_bounds = None
                relation = "UNRESOLVED"
            else:
                b = ds.bounds
                wgs84_bounds = transform_bounds(ds.crs, "EPSG:4326", b.left, b.bottom, b.right, b.top, densify_pts=21)
                relation = _relation(tuple(float(v) for v in wgs84_bounds))
            row = {
                "url": url,
                "filename": name,
                "size_bytes": size,
                "sha256": sha256,
                "driver": ds.driver,
                "width": ds.width,
                "height": ds.height,
                "count": ds.count,
                "crs": ds.crs.to_string() if ds.crs else None,
                "bounds_native": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
                "bounds_wgs84": list(wgs84_bounds) if wgs84_bounds else None,
                "nodata": ds.nodata,
                "dtypes": list(ds.dtypes),
                "aoi_relation": relation,
            }
        if relation in {"FULLY_WITHIN", "PARTIAL", "TOUCH_ONLY"}:
            shutil.copy2(path, selected_dir / name)
        rows.append(row)

    selected = [r for r in rows if r["aoi_relation"] in {"FULLY_WITHIN", "PARTIAL", "TOUCH_ONLY"}]
    unresolved = [r for r in rows if r["aoi_relation"] == "UNRESOLVED"]
    manifest = {
        "receipt_version": "0.1",
        "survey_id": "W00247",
        "source_landing_url": LANDING,
        "bounded_aoi_wgs84": [AOI.min_lon, AOI.min_lat, AOI.max_lon, AOI.max_lat],
        "bag_count": len(rows),
        "intersecting_bag_count": len(selected),
        "unresolved_bag_count": len(unresolved),
        "bags": rows,
        "state": "PASS" if not unresolved else "UNRESOLVED",
        "vertical_binding": "Filename declares MLLW; product-specific metadata remains authoritative and must be checked before cross-dataset depth subtraction.",
        "certification_boundary": "Raster bounds and byte identity only; intersection is coverage evidence, not confirmation of any rendered seafloor feature.",
    }
    (out / "w00247_bag_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
