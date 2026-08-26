#!/usr/bin/env python3
"""Intersect NCEI multibeam footprint polygons with the selected W00247 BAG envelope."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

from pipeline.marine_sources import default_transport, freeze_http_response

BBOX = (-65.9833772516194, 17.723098751773474, -65.82659038887648, 17.873293497881694)
FROZEN_SURVEYS = {
    "AT20", "EX1502L3", "EX1811", "EX2203", "EX2206", "KN151L4", "KN173L02",
    "NF-14-01T", "NF1501", "NF2202", "RB0604", "RC2605", "TN390",
}
BASE = "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_footprints/MapServer/0/query"


def main() -> int:
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": ",".join(str(v) for v in BBOX),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": "2000",
    }
    url = f"{BASE}?{urlencode(params)}"
    frozen = default_transport(url)
    if not 200 <= frozen.status < 300:
        raise ValueError(f"footprint query HTTP {frozen.status}")
    payload = json.loads(frozen.body.decode("utf-8"))
    if "error" in payload:
        raise ValueError(f"footprint service error: {payload['error']!r}")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("footprint service missing features")

    out = Path("evidence/marine/w00247_multibeam_footprints_v0_1")
    out.mkdir(parents=True, exist_ok=True)
    raw, sidecar = freeze_http_response(frozen, out, stem="multibeam_footprints")
    rows: list[dict[str, object]] = []
    frozen_matches: list[dict[str, object]] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("footprint feature must be object")
        attrs = feature.get("attributes") if isinstance(feature.get("attributes"), dict) else {}
        row = {"attributes": attrs, "geometry": feature.get("geometry")}
        rows.append(row)
        identity_values = {str(v) for v in attrs.values() if v is not None}
        if FROZEN_SURVEYS & identity_values:
            frozen_matches.append(row)

    manifest = {
        "receipt_version": "0.1",
        "selected_w00247_bag_bbox_wgs84": list(BBOX),
        "request_url": url,
        "response_sha256": frozen.response_sha256,
        "response_size": frozen.response_size,
        "raw_body": str(raw),
        "manifest": str(sidecar),
        "intersecting_footprint_feature_count": len(rows),
        "frozen_denominator_intersections": frozen_matches,
        "frozen_denominator_intersection_count": len(frozen_matches),
        "state": "PASS",
        "certification_boundary": "NCEI footprint-polygon intersection is a spatial candidate gate. A footprint match is not direct depth evidence and must be followed by byte-level product acquisition from the same stable survey identity.",
    }
    (out / "footprint_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
