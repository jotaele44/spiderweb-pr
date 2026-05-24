#!/usr/bin/env python3
"""Generate point and metric AOI buffers for a site-confidence record.

The script reads data/sites/<site_id>/site_record.json and exports:
- <site_id>_point.geojson
- <site_id>_AOI_250m.geojson
- <site_id>_AOI_500m.geojson

No silent demo substitution: missing dependencies or missing site records exit nonzero.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    from pyproj import Transformer
    from shapely.geometry import Point, mapping
except ImportError as exc:
    print("Missing dependency for AOI generation:", exc, file=sys.stderr)
    print("Install with: pip install shapely pyproj", file=sys.stderr)
    sys.exit(2)

WGS84 = "EPSG:4326"
WEB_MERCATOR = "EPSG:3857"


def load_site(site_id: str) -> dict:
    path = Path("data") / "sites" / site_id / "site_record.json"
    if not path.exists():
        raise FileNotFoundError(f"Site record not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def feature_collection(geometry, properties: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(geometry),
                "properties": properties,
            }
        ],
    }


def metric_buffer(lon: float, lat: float, radius_m: float):
    """Buffer using EPSG:3857 metric coordinates, then return EPSG:4326 geometry.

    EPSG:3857 is acceptable for small AOI seed generation. Downstream precision-critical
    processing should reproject to a local Puerto Rico CRS before raster/statistical work.
    """
    to_m = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    to_ll = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True)
    x, y = to_m.transform(lon, lat)
    buffered = Point(x, y).buffer(radius_m, resolution=96)
    coords = []
    for bx, by in buffered.exterior.coords:
        blon, blat = to_ll.transform(bx, by)
        coords.append((blon, blat))
    from shapely.geometry import Polygon
    return Polygon(coords)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate point and AOI GeoJSON files for a site.")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--radii", nargs="*", type=float, default=[250.0, 500.0])
    args = parser.parse_args()

    site = load_site(args.site_id)
    lat = float(site["latitude"])
    lon = float(site["longitude"])
    out_dir = Path("data") / "sites" / args.site_id

    point = Point(lon, lat)
    point_props = {
        "site_id": args.site_id,
        "name": site.get("name"),
        "geometry_role": "site_point",
        "crs": WGS84,
        "source": site.get("source_platform"),
    }
    write_json(out_dir / f"{args.site_id}_point.geojson", feature_collection(point, point_props))

    for radius in args.radii:
        radius_int = int(radius)
        poly = metric_buffer(lon, lat, radius)
        props = {
            "site_id": args.site_id,
            "name": site.get("name"),
            "geometry_role": "aoi_buffer",
            "radius_m": radius,
            "crs": WGS84,
            "buffer_method": "EPSG:4326 -> EPSG:3857 metric buffer -> EPSG:4326",
            "area_m2_approx": math.pi * radius * radius,
        }
        write_json(out_dir / f"{args.site_id}_AOI_{radius_int}m.geojson", feature_collection(poly, props))

    print(f"Generated AOI GeoJSON files for {args.site_id} in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
