from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("geopandas")
pytest.importorskip("pyproj")
pytest.importorskip("shapely")

from spiderweb.ssurgo_spatial import certify_exact_spatial_denominator


def _write_geojson(path: Path, features: list[dict]) -> bytes:
    payload = json.dumps({
        "type": "FeatureCollection",
        "features": features,
    }).encode("utf-8")
    path.write_bytes(payload)
    return payload


def _receipt(role: str, raw: bytes) -> dict:
    return {
        "provider_id": "SSURGO_SOILS",
        "request_role": role,
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _polygon(west: float, south: float, east: float, north: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]],
    }


def test_exact_radius_excludes_bbox_corner_mapunit(tmp_path: Path) -> None:
    survey_path = tmp_path / "survey.geojson"
    mapunit_path = tmp_path / "mapunit.geojson"

    survey_raw = _write_geojson(
        survey_path,
        [{
            "type": "Feature",
            "properties": {"areasymbol": "TEST"},
            "geometry": _polygon(-66.02, 17.98, -65.98, 18.02),
        }],
    )

    mapunit_raw = _write_geojson(
        mapunit_path,
        [
            {
                "type": "Feature",
                "properties": {
                    "mukey": "100",
                    "mupolygonkey": "1000",
                },
                "geometry": _polygon(
                    -66.003, 17.997, -65.997, 18.003
                ),
            },
            {
                "type": "Feature",
                "properties": {
                    "mukey": "200",
                    "mupolygonkey": "2000",
                },
                # Inside the WFS radius envelope but outside the 1 km circle.
                "geometry": _polygon(
                    -65.9920, 18.0070, -65.9906, 18.0085
                ),
            },
        ],
    )

    result = certify_exact_spatial_denominator(
        query={
            "query_id": "radius",
            "geometry": {
                "type": "radius",
                "lat": 18.0,
                "lon": -66.0,
                "radius_m": 1000,
            },
            "allow_partial": False,
        },
        survey_raw_path=survey_path,
        survey_receipt=_receipt("SurveyAreaPoly", survey_raw),
        mapunit_raw_path=mapunit_path,
        mapunit_receipt=_receipt("MapunitPoly", mapunit_raw),
    )

    assert result["state"] == "PASS"
    assert result["survey_coverage"]["complete"] is True
    assert result["survey_coverage"]["coverage_fraction"] > 0.999999
    assert result["selection"]["mapunit_source_row_count"] == 2
    assert result["selection"]["retained_polygon_row_count"] == 1
    assert result["selection"]["mukey_count"] == 1
    assert result["selection"]["mukeys"] == ["100"]
    assert result["selection"]["mupolygonkey_state"] == "UNIQUE_NON_NULL"
    assert result["policy"]["positive_area_required_for_area_aoi"] is True


def test_exact_spatial_rejects_incomplete_survey_coverage(tmp_path: Path) -> None:
    survey_path = tmp_path / "survey.geojson"
    mapunit_path = tmp_path / "mapunit.geojson"

    survey_raw = _write_geojson(
        survey_path,
        [{
            "type": "Feature",
            "properties": {"areasymbol": "TEST"},
            "geometry": _polygon(-66.01, 17.99, -66.0, 18.01),
        }],
    )
    mapunit_raw = _write_geojson(
        mapunit_path,
        [{
            "type": "Feature",
            "properties": {
                "mukey": "100",
                "mupolygonkey": "1000",
            },
            "geometry": _polygon(-66.01, 17.99, -65.99, 18.01),
        }],
    )

    with pytest.raises(
        ValueError,
        match="SurveyArea coverage incomplete",
    ):
        certify_exact_spatial_denominator(
            query={
                "query_id": "coverage",
                "geometry": {
                    "type": "bbox",
                    "west": -66.01,
                    "south": 17.99,
                    "east": -65.99,
                    "north": 18.01,
                },
                "allow_partial": False,
            },
            survey_raw_path=survey_path,
            survey_receipt=_receipt("SurveyAreaPoly", survey_raw),
            mapunit_raw_path=mapunit_path,
            mapunit_receipt=_receipt("MapunitPoly", mapunit_raw),
        )
