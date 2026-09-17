from __future__ import annotations

import json
from pathlib import Path

import pytest

from spiderweb.location_query import LocationQueryError, load_registry, route_query, validate_query


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs/location_query_providers.json"


def test_registry_has_bounded_provider_denominator() -> None:
    registry = load_registry(REGISTRY_PATH)
    providers = registry["providers"]
    expected = {
        "USGS_3DEP_1M",
        "PRVI_1m_DEM_2018",
        "NCEI_COASTAL_DEM",
        "NASA_GIBS_IMAGERY",
        "SENTINEL_HUB_IMAGERY",
        "COPERNICUS_CDSE_IMAGERY",
        "PRPB_GEOLOGY_KARST",
        "PR_AQUIFERS_WELLS_SPRINGS",
        "PR_MARINE_LIDAR_TOPOBATHY",
        "SSURGO_SOILS",
        "USGS_3DHP_NHD",
        "USFWS_NWI",
        "FEMA_NFHL",
        "USACE_GENERAL_GIS",
    }
    assert set(providers) == expected
    assert len(providers) == 14


def test_bbox_plan_routes_without_fetching() -> None:
    query = {
        "query_id": "fixture-bbox",
        "geometry": {
            "type": "bbox",
            "west": -66.10,
            "south": 18.20,
            "east": -65.90,
            "north": 18.45,
        },
        "mode": "plan",
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["query"]["mode"] == "plan"
    assert plan["provider_denominator_count"] > 0
    assert plan["policy"]["plan_before_download"] is True
    assert plan["policy"]["no_coverage_is_not_source_absence"] is True


def test_imagery_credentials_are_explicit_state() -> None:
    query = {
        "query_id": "fixture-imagery",
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
        "families": ["satellite_imagery"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    by_id = {row["provider_id"]: row for row in plan["providers"]}
    assert by_id["NASA_GIBS_IMAGERY"]["route_state"] == "ROUTABLE"
    assert by_id["SENTINEL_HUB_IMAGERY"]["route_state"] == "CREDENTIAL_REQUIRED"
    assert by_id["COPERNICUS_CDSE_IMAGERY"]["route_state"] == "CREDENTIAL_REQUIRED"


def test_missing_family_is_not_synthesized() -> None:
    query = {
        "query_id": "fixture-none",
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
        "families": ["does_not_exist"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["provider_denominator_count"] == 0
    assert plan["providers"] == []


def test_invalid_bbox_fails_closed() -> None:
    with pytest.raises(LocationQueryError):
        validate_query(
            {
                "query_id": "bad-bbox",
                "geometry": {
                    "type": "bbox",
                    "west": -65.0,
                    "south": 18.0,
                    "east": -66.0,
                    "north": 18.5,
                },
            }
        )


def test_radius_requires_positive_distance() -> None:
    with pytest.raises(LocationQueryError):
        validate_query(
            {
                "query_id": "bad-radius",
                "geometry": {
                    "type": "radius",
                    "lat": 18.3,
                    "lon": -66.0,
                    "radius_m": 0,
                },
            }
        )
