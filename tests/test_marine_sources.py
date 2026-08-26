from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from pipeline.marine_sources import (
    BoundingBox,
    CatalogFamily,
    FrozenHttpResponse,
    build_ncei_catalog_url,
    build_nos_bag_query_url,
    fetch_all_ncei_catalog_pages,
    fetch_all_nos_bag_pages,
    fetch_ncei_catalog_page,
    fetch_nos_bag_page,
    freeze_http_response,
)


AOI = BoundingBox(-66.25, 17.80, -65.75, 18.10)


def frozen(url: str, payload: object, *, status: int = 200) -> FrozenHttpResponse:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    return FrozenHttpResponse(
        request_url=url,
        status=status,
        retrieved_utc="2026-08-15T04:00:00+00:00",
        response_sha256=hashlib.sha256(body).hexdigest(),
        response_size=len(body),
        headers={"Content-Type": "application/json"},
        body=body,
    )


def test_bbox_rejects_inverted_extent() -> None:
    with pytest.raises(ValueError, match="minimums"):
        BoundingBox(-65.0, 18.0, -66.0, 17.0)


def test_ncei_query_preserves_bbox_and_paging() -> None:
    url = build_ncei_catalog_url(
        CatalogFamily.MULTIBEAM,
        AOI,
        offset=100,
        page_size=50,
        start_year=2000,
        end_year=2026,
    )
    parsed = parse_qs(urlparse(url).query)

    assert parsed["geometry"] == ["-66.25,17.8,-65.75,18.1"]
    assert parsed["offset"] == ["100"]
    assert parsed["max"] == ["50"]
    assert parsed["startYear"] == ["2000"]
    assert parsed["endYear"] == ["2026"]


def test_nos_bag_query_uses_wgs84_envelope_and_stable_order() -> None:
    url = build_nos_bag_query_url(AOI, offset=2000, page_size=2000)
    parsed = parse_qs(urlparse(url).query)

    assert parsed["geometry"] == ["-66.25,17.8,-65.75,18.1"]
    assert parsed["geometryType"] == ["esriGeometryEnvelope"]
    assert parsed["inSR"] == ["4326"]
    assert parsed["outSR"] == ["4326"]
    assert parsed["resultOffset"] == ["2000"]
    assert parsed["resultRecordCount"] == ["2000"]
    assert parsed["orderByFields"] == ["SURVEY_ID ASC"]


def test_ncei_page_rejects_non_object_item() -> None:
    def transport(url: str) -> FrozenHttpResponse:
        return frozen(url, {"items": ["not-an-object"], "count": 1})

    with pytest.raises(ValueError, match="must be JSON objects"):
        fetch_ncei_catalog_page(
            CatalogFamily.MULTIBEAM, AOI, transport=transport
        )


def test_ncei_pagination_closes_exact_count_without_synthesizing_rows() -> None:
    rows = [
        {"surveyId": "A", "platform": "p1"},
        {"surveyId": "B", "platform": "p2"},
        {"surveyId": "C", "platform": "p3"},
    ]

    def transport(url: str) -> FrozenHttpResponse:
        query = parse_qs(urlparse(url).query)
        offset = int(query["offset"][0])
        size = int(query["max"][0])
        return frozen(url, {"items": rows[offset : offset + size], "count": 3})

    pages = fetch_all_ncei_catalog_pages(
        CatalogFamily.MULTIBEAM, AOI, page_size=2, transport=transport
    )

    assert len(pages) == 2
    assert sum(len(page.items) for page in pages) == 3
    assert [item["surveyId"] for page in pages for item in page.items] == [
        "A",
        "B",
        "C",
    ]


def test_ncei_pagination_fails_closed_when_count_changes() -> None:
    calls = 0

    def transport(url: str) -> FrozenHttpResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return frozen(url, {"items": [{"surveyId": "A"}], "count": 2})
        return frozen(url, {"items": [{"surveyId": "B"}], "count": 3})

    with pytest.raises(ValueError, match="count changed"):
        fetch_all_ncei_catalog_pages(
            CatalogFamily.SOUNDING, AOI, page_size=1, transport=transport
        )


def test_ncei_empty_result_is_bounded_zero_when_count_is_zero() -> None:
    def transport(url: str) -> FrozenHttpResponse:
        return frozen(url, {"items": [], "count": 0})

    pages = fetch_all_ncei_catalog_pages(
        CatalogFamily.MULTIBEAM, AOI, transport=transport
    )

    assert len(pages) == 1
    assert pages[0].total_count == 0
    assert pages[0].items == ()


def test_arcgis_transfer_limit_paginates_whole_features() -> None:
    features = [
        {"attributes": {"SURVEY_ID": "H1"}, "geometry": {"rings": []}},
        {"attributes": {"SURVEY_ID": "H2"}, "geometry": {"rings": []}},
        {"attributes": {"SURVEY_ID": "H3"}, "geometry": {"rings": []}},
    ]

    def transport(url: str) -> FrozenHttpResponse:
        query = parse_qs(urlparse(url).query)
        offset = int(query["resultOffset"][0])
        size = int(query["resultRecordCount"][0])
        page = features[offset : offset + size]
        exceeded = offset + len(page) < len(features)
        return frozen(
            url,
            {"features": page, "exceededTransferLimit": exceeded},
        )

    pages = fetch_all_nos_bag_pages(AOI, page_size=2, transport=transport)

    assert len(pages) == 2
    assert [
        feature["attributes"]["SURVEY_ID"]
        for page in pages
        for feature in page.features
    ] == ["H1", "H2", "H3"]


def test_arcgis_error_object_fails_closed() -> None:
    def transport(url: str) -> FrozenHttpResponse:
        return frozen(url, {"error": {"code": 400, "message": "bad query"}})

    with pytest.raises(ValueError, match="error object"):
        fetch_nos_bag_page(AOI, transport=transport)


def test_freeze_persists_exact_bytes_and_manifest(tmp_path: Path) -> None:
    payload = {"items": [{"surveyId": "H12345"}], "count": 1}
    response = frozen("https://example.test/query", payload)

    body_path, manifest_path = freeze_http_response(
        response, tmp_path, stem="ncei-page-000"
    )

    assert body_path.read_bytes() == response.body
    assert hashlib.sha256(body_path.read_bytes()).hexdigest() == response.response_sha256
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["request_url"] == "https://example.test/query"
    assert manifest["response_sha256"] == response.response_sha256
    assert manifest["response_size"] == len(response.body)


def test_http_failure_is_not_zero_data() -> None:
    def transport(url: str) -> FrozenHttpResponse:
        return frozen(url, {"items": [], "count": 0}, status=503)

    with pytest.raises(ValueError, match="HTTP status"):
        fetch_ncei_catalog_page(
            CatalogFamily.MULTIBEAM, AOI, transport=transport
        )
