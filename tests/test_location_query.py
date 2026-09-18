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
        "FEMA_PR_ABFE_1PCT",
        "USACE_GENERAL_GIS",
        "USACE_PORTS_NAV",
    }
    assert set(providers) == expected
    assert len(providers) == 16


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


def test_ssurgo_plan_emits_two_bounded_wfs_requests() -> None:
    query = {
        "query_id": "fixture-ssurgo",
        "geometry": {"type": "bbox", "west": -66.05, "south": 18.29, "east": -65.93, "north": 18.39},
        "families": ["soils"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["request_count"] == 2
    roles = {row["request_role"] for row in plan["requests"]}
    assert roles == {"SurveyAreaPoly", "MapunitPoly"}
    assert all(row["provider_id"] == "SSURGO_SOILS" for row in plan["requests"])


def test_nwi_freezes_live_service_denominator_before_layer_query() -> None:
    query = {
        "query_id": "fixture-nwi",
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
        "families": ["wetlands"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["provider_denominator_count"] == 1
    assert plan["providers"][0]["route_state"] == "RESOLVER_ONLY"
    assert plan["request_count"] == 1
    assert plan["requests"][0]["identity_state"] == "DISCOVERY_FOR_LAYER_DENOMINATOR"
    assert plan["requests"][0]["url"].endswith("/rest?f=json")


def test_3dhp_remains_resolver_only_and_freezes_metadata_first() -> None:
    query = {
        "query_id": "fixture-3dhp",
        "geometry": {"type": "bbox", "west": -66.1, "south": 18.2, "east": -65.9, "north": 18.4},
        "families": ["hydrography"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["providers"][0]["route_state"] == "RESOLVER_ONLY"
    assert plan["request_count"] == 1
    assert plan["requests"][0]["identity_state"] == "DISCOVERY_FOR_LAYER_DENOMINATOR"


def test_usace_ports_navigation_has_four_bound_source_requests() -> None:
    query = {
        "query_id": "fixture-usace-ports",
        "geometry": {"type": "bbox", "west": -66.2, "south": 18.1, "east": -65.8, "north": 18.5},
        "families": ["ports_navigation"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["request_count"] == 4
    assert {r["request_role"] for r in plan["requests"]} == {
        "ports", "principal_ports", "navigation_facilities", "waterway_network_nodes"
    }


def test_geology_reuses_existing_source_denominator() -> None:
    query = {
        "query_id": "fixture-geology",
        "geometry": {"type": "bbox", "west": -66.8, "south": 17.9, "east": -66.4, "north": 18.3},
        "families": ["geology_karst"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["providers"][0]["route_state"] == "ROUTABLE"
    roles = {r["request_role"] for r in plan["requests"]}
    assert {"PRPB_GEOLOGY_3", "PRPB_SINKHOLES_4", "PRPB_CAVES_31"} <= roles


def test_hydrogeology_reuses_stable_id_source_specs() -> None:
    query = {
        "query_id": "fixture-hydrogeo",
        "geometry": {"type": "bbox", "west": -66.2, "south": 18.1, "east": -65.8, "north": 18.5},
        "families": ["hydrogeology"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["providers"][0]["route_state"] == "ROUTABLE"
    assert plan["request_count"] >= 5
    assert all("stable_id_fields" in r for r in plan["requests"])


def test_ssurgo_is_resolver_only_until_tabular_chain_is_in_repo() -> None:
    query = {
        "query_id": "fixture-ssurgo-state",
        "geometry": {"type": "bbox", "west": -66.05, "south": 18.29, "east": -65.93, "north": 18.39},
        "families": ["soils"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["providers"][0]["route_state"] == "RESOLVER_ONLY"
    assert plan["request_count"] == 2

def test_fema_pr_abfe_is_bounded_resolver_not_nfhl_substitute() -> None:
    query = {
        "query_id": "fixture-fema-abfe",
        "geometry": {"type": "bbox", "west": -67.0, "south": 17.8, "east": -65.5, "north": 18.6},
        "families": ["flood_hazard"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    by_id = {row["provider_id"]: row for row in plan["providers"]}
    assert by_id["FEMA_PR_ABFE_1PCT"]["route_state"] == "RESOLVER_ONLY"
    assert by_id["FEMA_NFHL"]["route_state"] == "RESOLVER_ONLY"
    roles = {row["request_role"] for row in plan["requests"]}
    assert "abfe_map_service_denominator" in roles
    assert "nfhl_wms_capabilities" in roles
