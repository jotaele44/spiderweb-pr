from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from gebco.marine_evidence import CoverageState, ProductStage, SensorType, VerticalReference
from pipeline.marine_lidar_sources import (
    LidarInventoryLayer,
    build_usiei_query_url,
    fetch_all_usiei_pages,
    fetch_bulk_url_manifest,
    parse_url_list,
)
from pipeline.marine_observation_binding import (
    bind_measured_sample,
    bind_usiei_inventory_feature,
    inventory_binding_to_observation,
)
from pipeline.marine_sources import BoundingBox, FrozenHttpResponse


BBOX = BoundingBox(-66.3, 17.85, -65.8, 18.1)


def frozen(url: str, payload: object, *, status: int = 200) -> FrozenHttpResponse:
    body = json.dumps(payload).encode()
    import hashlib

    return FrozenHttpResponse(
        request_url=url,
        status=status,
        retrieved_utc="2026-08-16T05:00:00+00:00",
        response_sha256=hashlib.sha256(body).hexdigest(),
        response_size=len(body),
        headers={},
        body=body,
    )


def test_usiei_query_is_bounded_and_requests_geometry() -> None:
    url = build_usiei_query_url(LidarInventoryLayer.TOPOBATHY_SHORELINE, BBOX)
    assert "geometryType=esriGeometryEnvelope" in url
    assert "returnGeometry=true" in url
    assert "outSR=4326" in url
    assert "orderByFields=OBJECTID+ASC" in url


def test_usiei_pagination_preserves_all_features() -> None:
    calls = 0

    def transport(url: str) -> FrozenHttpResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            payload = {
                "features": [
                    {"attributes": {"OBJECTID": 1}},
                    {"attributes": {"OBJECTID": 2}},
                ],
                "exceededTransferLimit": True,
            }
        else:
            payload = {
                "features": [{"attributes": {"OBJECTID": 3}}],
                "exceededTransferLimit": False,
            }
        return frozen(url, payload)

    pages = fetch_all_usiei_pages(
        LidarInventoryLayer.BATHYMETRIC,
        BBOX,
        page_size=2,
        transport=transport,
    )
    assert [p.offset for p in pages] == [0, 2]
    assert sum(len(p.features) for p in pages) == 3


def test_usiei_transfer_limit_on_empty_page_fails_closed() -> None:
    def transport(url: str) -> FrozenHttpResponse:
        return frozen(url, {"features": [], "exceededTransferLimit": True})

    with pytest.raises(ValueError, match="empty page"):
        fetch_all_usiei_pages(
            LidarInventoryLayer.BATHYMETRIC, BBOX, transport=transport
        )


def test_bulk_url_list_requires_https_and_uniqueness() -> None:
    assert parse_url_list(b"https://example.test/a.tif\n") == (
        "https://example.test/a.tif",
    )
    with pytest.raises(ValueError, match="absolute HTTPS"):
        parse_url_list(b"http://example.test/a.tif\n")
    with pytest.raises(ValueError, match="duplicate"):
        parse_url_list(b"https://example.test/a\nhttps://example.test/a\n")


def test_bulk_manifest_freezes_url_list_identity() -> None:
    body = b"https://example.test/a.tif\nhttps://example.test/b.tif\n"

    def transport(url: str) -> FrozenHttpResponse:
        import hashlib

        return FrozenHttpResponse(
            request_url=url,
            status=200,
            retrieved_utc="2026-08-16T05:00:00+00:00",
            response_sha256=hashlib.sha256(body).hexdigest(),
            response_size=len(body),
            headers={},
            body=body,
        )

    manifest = fetch_bulk_url_manifest(
        "8571", "https://example.test/urllist8571.txt", transport=transport
    )
    assert manifest.dataset_id == "8571"
    assert len(manifest.assets) == 2
    assert manifest.frozen.response_size == len(body)


def sample_feature() -> dict[str, object]:
    return {
        "attributes": {
            "OBJECTID": 101,
            "GlobalID": "{A-B-C}",
            "ProjectName": "Puerto Rico topobathy",
            "HorizontalDatum": "NAD83(2011)",
            "VerticalDatum": "PRVD02",
            "CollectionDate": "2018",
            "MetadataLink": "https://example.test/meta",
            "DataAccess": "https://example.test/data",
        },
        "geometry": {"rings": []},
    }


def test_inventory_binding_never_becomes_direct_measurement() -> None:
    binding = bind_usiei_inventory_feature(
        LidarInventoryLayer.TOPOBATHY_SHORELINE, sample_feature()
    )
    obs = inventory_binding_to_observation(binding)
    assert obs.sensor is SensorType.TOPOBATHYMETRIC_LIDAR
    assert obs.stage is ProductStage.DERIVED_PRODUCT
    assert obs.coverage is CoverageState.UNKNOWN
    assert obs.value_m is None
    assert obs.is_direct_sensor_observation is False


def test_inventory_binding_requires_authoritative_stable_identifier() -> None:
    feature = {"attributes": {"ProjectName": "same name is not identity"}}
    with pytest.raises(ValueError, match="stable identifier"):
        bind_usiei_inventory_feature(LidarInventoryLayer.BATHYMETRIC, feature)


def test_direct_sample_requires_hash_and_bound_vertical_reference() -> None:
    reference = VerticalReference(
        horizontal_crs="EPSG:4326",
        vertical_crs=None,
        vertical_datum="MLLW",
        tidal_datum="MLLW",
        depth_positive="down",
    )
    obs = bind_measured_sample(
        observation_id="sample-1",
        sensor=SensorType.MULTIBEAM_ECHOSOUNDER,
        root_survey_id="survey-1",
        vertical_reference=reference,
        value_m=12.5,
        uncertainty_m=0.2,
        observed_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_uri="https://example.test/raw.bin",
        source_sha256="a" * 64,
    )
    assert obs.coverage is CoverageState.DIRECTLY_OBSERVED
    assert obs.is_direct_sensor_observation is True


def test_direct_sample_rejects_unbound_vertical_reference() -> None:
    reference = VerticalReference(
        horizontal_crs="EPSG:4326",
        vertical_crs=None,
        vertical_datum=None,
        tidal_datum=None,
        depth_positive="down",
    )
    with pytest.raises(ValueError, match="bound vertical reference"):
        bind_measured_sample(
            observation_id="sample-1",
            sensor=SensorType.BATHYMETRIC_LIDAR,
            root_survey_id="survey-1",
            vertical_reference=reference,
            value_m=1.0,
            uncertainty_m=None,
            observed_at=None,
            source_uri="https://example.test/raw.bin",
            source_sha256="b" * 64,
        )
