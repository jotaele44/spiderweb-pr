from __future__ import annotations

import json

from pipeline.marine_alternate_products import (
    parse_nos_product_links,
    parse_stac_item_collection,
)
from pipeline.marine_sources import BoundingBox, FrozenHttpResponse


def _frozen(url: str, body: bytes) -> FrozenHttpResponse:
    return FrozenHttpResponse(
        request_url=url,
        status=200,
        retrieved_utc="2026-08-16T00:00:00+00:00",
        response_sha256="0" * 64,
        response_size=len(body),
        headers={},
        body=body,
    )


def test_nos_product_links_preserve_product_urls() -> None:
    html = b'<a href="W00247_MB_2m_MLLW_1of4.bag">BAG</a><a href="W00247.xml">XML</a>'
    result = parse_nos_product_links(_frozen("https://example.test/nos/W00247.html", html))
    assert [item["kind"] for item in result.assets] == ["bag", "xml"]
    assert result.assets[0]["url"].endswith("W00247_MB_2m_MLLW_1of4.bag")


def test_stac_bbox_selection_is_bounded() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"id": "inside", "bbox": [-66.1, 17.7, -66.0, 17.8], "assets": {}},
            {"id": "outside", "bbox": [-67.0, 18.5, -66.9, 18.6], "assets": {}},
        ],
    }
    frozen = _frozen("https://example.test/items.json", json.dumps(payload).encode())
    result = parse_stac_item_collection(
        frozen, BoundingBox(-66.2, 17.5, -65.8, 18.05)
    )
    assert [feature["id"] for feature in result.assets] == ["inside"]


def test_stac_geometry_fallback_handles_polygon() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "id": "poly",
            "geometry": {"type": "Polygon", "coordinates": [[[-66.1,17.6],[-66.0,17.6],[-66.0,17.7],[-66.1,17.6]]]},
            "assets": {},
        }],
    }
    result = parse_stac_item_collection(
        _frozen("https://example.test/items.json", json.dumps(payload).encode()),
        BoundingBox(-66.2, 17.5, -65.8, 18.05),
    )
    assert len(result.assets) == 1
