import hashlib
import json
from pathlib import Path

import pytest

from spiderweb.subsurface.benchmark_acquisition import (
    arcgis_bbox_query,
    arcgis_point_query,
    freeze_http_response,
    ogc_bbox_query,
    write_manifest,
)


def test_arcgis_point_query_is_deterministic_and_exact_anchor():
    url = arcgis_point_query(
        "https://sige.pr.gov/server/rest/services/MIPR/Geologia_v10_N/FeatureServer/3",
        lon=-67.1140566,
        lat=18.5091743,
    )
    assert "geometry=-67.1140566%2C18.5091743" in url
    assert "geometryType=esriGeometryPoint" in url
    assert "spatialRel=esriSpatialRelIntersects" in url
    assert url == arcgis_point_query(
        "https://sige.pr.gov/server/rest/services/MIPR/Geologia_v10_N/FeatureServer/3",
        lon=-67.1140566,
        lat=18.5091743,
    )


def test_bbox_queries_fail_closed_on_reversed_bounds():
    with pytest.raises(ValueError, match="bbox ordering"):
        arcgis_bbox_query(
            "https://example.gov/FeatureServer/1",
            west=-67.0,
            south=18.5,
            east=-67.2,
            north=18.6,
        )
    with pytest.raises(ValueError, match="bbox ordering"):
        ogc_bbox_query(
            "https://example.gov/collections/sites/items",
            west=-67.0,
            south=18.5,
            east=-67.2,
            north=18.6,
        )


def test_free_response_is_content_addressed_and_idempotent(tmp_path: Path):
    raw = b'{"features":[]}'
    row1 = freeze_http_response(
        source_id="TEST_SOURCE",
        request_url="https://example.gov/query",
        raw=raw,
        http_status=200,
        content_type="application/json",
        output_dir=tmp_path,
        retrieval_utc="2026-09-11T15:00:00+00:00",
    )
    row2 = freeze_http_response(
        source_id="TEST_SOURCE",
        request_url="https://example.gov/query",
        raw=raw,
        http_status=200,
        content_type="application/json",
        output_dir=tmp_path,
        retrieval_utc="2026-09-11T15:01:00+00:00",
    )
    expected = hashlib.sha256(raw).hexdigest()
    assert row1.sha256 == expected
    assert row1.reused_existing_bytes is False
    assert row2.reused_existing_bytes is True
    assert row1.raw_path == row2.raw_path
    assert Path(row1.raw_path).read_bytes() == raw


def test_free_response_rejects_empty_or_failed_http(tmp_path: Path):
    with pytest.raises(ValueError, match="empty response"):
        freeze_http_response(
            source_id="X",
            request_url="https://example.gov/x",
            raw=b"",
            http_status=200,
            content_type="application/json",
            output_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="non-success"):
        freeze_http_response(
            source_id="X",
            request_url="https://example.gov/x",
            raw=b"no",
            http_status=500,
            content_type="text/plain",
            output_dir=tmp_path,
        )


def test_manifest_has_deterministic_logical_hash(tmp_path: Path):
    a = freeze_http_response(
        source_id="B",
        request_url="https://example.gov/b",
        raw=b"b",
        http_status=200,
        content_type="application/octet-stream",
        output_dir=tmp_path / "raw",
        retrieval_utc="2026-09-11T15:00:00+00:00",
    )
    b = freeze_http_response(
        source_id="A",
        request_url="https://example.gov/a",
        raw=b"a",
        http_status=200,
        content_type="application/octet-stream",
        output_dir=tmp_path / "raw",
        retrieval_utc="2026-09-11T15:00:00+00:00",
    )
    p1 = write_manifest(tmp_path / "m1.json", [a, b])
    p2 = write_manifest(tmp_path / "m2.json", [b, a])
    assert p1["logical_sha256"] == p2["logical_sha256"]
    assert [row["source_id"] for row in p1["sources"]] == ["A", "B"]
    assert json.loads((tmp_path / "m1.json").read_text())["source_count"] == 2
