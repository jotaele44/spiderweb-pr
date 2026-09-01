from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from pipeline.marine_product_sources import (
    build_ncei_file_url,
    fetch_all_ncei_file_pages,
)
from pipeline.marine_sources import BoundingBox, CatalogFamily, FrozenHttpResponse


def _frozen(url: str, payload: dict[str, object]) -> FrozenHttpResponse:
    body = json.dumps(payload).encode()
    return FrozenHttpResponse(
        request_url=url,
        status=200,
        retrieved_utc="2026-08-16T00:00:00+00:00",
        response_sha256="0" * 64,
        response_size=len(body),
        headers={},
        body=body,
    )


def test_multibeam_file_url_can_preserve_aoi_filter() -> None:
    bbox = BoundingBox(-66.2, 17.5, -65.8, 18.05)
    url = build_ncei_file_url(
        CatalogFamily.MULTIBEAM,
        surveys=["AT20", "RC2605"],
        categories=["Point Data"],
        bbox=bbox,
        page_size=100,
    )
    query = parse_qs(urlparse(url).query)
    assert query["surveys"] == ["AT20,RC2605"]
    assert query["categories"] == ["Point Data"]
    assert query["geometry"] == ["-66.2,17.5,-65.8,18.05"]


def test_sounding_file_url_rejects_false_file_geometry_precision() -> None:
    with pytest.raises(ValueError, match="do not support file-level geometry"):
        build_ncei_file_url(
            CatalogFamily.SOUNDING,
            surveys=["W00247"],
            bbox=BoundingBox(-66.2, 17.5, -65.8, 18.05),
        )


def test_file_pagination_requires_stable_count_and_arithmetic_closure() -> None:
    payloads = {
        0: {"count": 3, "items": [{"surveyId": "A"}, {"surveyId": "B"}]},
        2: {"count": 3, "items": [{"surveyId": "C"}]},
    }

    def transport(url: str) -> FrozenHttpResponse:
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        return _frozen(url, payloads[offset])

    pages = fetch_all_ncei_file_pages(
        CatalogFamily.MULTIBEAM,
        surveys=["A", "B", "C"],
        page_size=2,
        transport=transport,
    )
    assert len(pages) == 2
    assert sum(len(page.items) for page in pages) == 3


def test_file_pagination_count_drift_fails_closed() -> None:
    payloads = {
        0: {"count": 3, "items": [{"surveyId": "A"}, {"surveyId": "B"}]},
        2: {"count": 4, "items": [{"surveyId": "C"}, {"surveyId": "D"}]},
    }

    def transport(url: str) -> FrozenHttpResponse:
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        return _frozen(url, payloads[offset])

    with pytest.raises(ValueError, match="count changed"):
        fetch_all_ncei_file_pages(
            CatalogFamily.MULTIBEAM,
            surveys=["A", "B"],
            page_size=2,
            transport=transport,
        )


def test_zero_file_result_is_bounded_success_not_transport_failure() -> None:
    def transport(url: str) -> FrozenHttpResponse:
        return _frozen(url, {"count": 0, "items": []})

    pages = fetch_all_ncei_file_pages(
        CatalogFamily.SOUNDING,
        surveys=["H01514"],
        categories=["Point Data"],
        transport=transport,
    )
    assert len(pages) == 1
    assert pages[0].total_count == 0
    assert pages[0].items == ()
