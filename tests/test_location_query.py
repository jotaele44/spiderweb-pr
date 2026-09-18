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


def test_nwi_bound_feature_layer_is_routable() -> None:
    query = {
        "query_id": "fixture-nwi",
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
        "families": ["wetlands"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["provider_denominator_count"] == 1
    assert plan["providers"][0]["route_state"] == "ROUTABLE"
    assert plan["request_count"] == 1
    assert plan["requests"][0]["identity_state"] == "SOURCE_MANIFESTATION"
    assert "/Wetlands/FeatureServer/0/query?" in plan["requests"][0]["url"]


def test_3dhp_remains_metadata_first_until_raw_denominator_freeze() -> None:
    query = {
        "query_id": "fixture-3dhp",
        "geometry": {"type": "bbox", "west": -66.1, "south": 18.2, "east": -65.9, "north": 18.4},
        "families": ["hydrography"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["providers"][0]["route_state"] == "RESOLVER_ONLY"
    assert plan["request_count"] == 1
    request = plan["requests"][0]
    assert request["request_role"] == "feature_service_metadata"
    assert request["identity_state"] == "DISCOVERY_FOR_LAYER_DENOMINATOR"
    assert request["url"].endswith("?f=json")


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


def test_ssurgo_requires_post_fetch_certification_stage() -> None:
    query = {
        "query_id": "fixture-ssurgo-state",
        "geometry": {"type": "bbox", "west": -66.05, "south": 18.29, "east": -65.93, "north": 18.39},
        "families": ["soils"],
        "mode": "fetch",
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    provider = plan["providers"][0]
    assert provider["route_state"] == "ROUTABLE"
    assert provider["execution_kind"] == "REQUEST_SPECS_PLUS_POSTPROCESSOR"
    assert provider["generic_executor_ready"] is False
    assert plan["request_count"] == 2
    assert plan["fetch_gate"] == "BLOCKED_INCOMPLETE_PROVIDER_EXECUTION"
    assert plan["execution_gap_provider_ids"] == ["SSURGO_SOILS"]

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


def test_usace_general_emits_service_denominator_request() -> None:
    query = {
        "query_id": "fixture-usace-general",
        "geometry": {"type": "bbox", "west": -67.3, "south": 17.8, "east": -65.2, "north": 18.6},
        "families": ["federal_infrastructure"],
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["providers"][0]["route_state"] == "RESOLVER_ONLY"
    assert plan["request_count"] == 1
    request = plan["requests"][0]
    assert request["request_role"] == "services_root_denominator"
    assert request["identity_state"] == "DISCOVERY_FOR_SERVICE_DENOMINATOR"
    assert request["url"].endswith("?f=pjson")


def test_fetch_gate_ready_for_fully_generic_nwi_query() -> None:
    query = {
        "query_id": "fixture-nwi-fetch",
        "geometry": {"type": "bbox", "west": -66.1, "south": 18.2, "east": -65.9, "north": 18.4},
        "families": ["wetlands"],
        "mode": "fetch",
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["fetch_gate"] == "READY"
    assert plan["generic_executor_provider_ids"] == ["USFWS_NWI"]
    assert plan["fetch_blocker_provider_ids"] == []


def test_fetch_gate_blocks_specialized_adapter_gap() -> None:
    query = {
        "query_id": "fixture-gibs-fetch",
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
        "families": ["satellite_imagery"],
        "mode": "fetch",
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["fetch_gate"] == "BLOCKED_INCOMPLETE_PROVIDER_EXECUTION"
    assert "NASA_GIBS_IMAGERY" in plan["execution_gap_provider_ids"]
    assert "NASA_GIBS_IMAGERY" in plan["specialized_adapter_provider_ids"]


def test_allow_partial_makes_execution_gaps_explicit_not_silent() -> None:
    query = {
        "query_id": "fixture-partial",
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
        "mode": "fetch",
        "allow_partial": True,
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["fetch_gate"] == "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"
    assert plan["fetch_blocker_provider_ids"]
    assert plan["execution_gap_provider_ids"]


def test_plan_mode_never_claims_fetch_ready() -> None:
    query = {
        "query_id": "fixture-plan-gate",
        "geometry": {"type": "bbox", "west": -66.1, "south": 18.2, "east": -65.9, "north": 18.4},
        "families": ["wetlands"],
        "mode": "plan",
    }
    plan = route_query(query, registry=load_registry(REGISTRY_PATH), env={})
    assert plan["fetch_gate"] == "NOT_REQUESTED"


def test_nonboolean_allow_partial_fails_closed() -> None:
    with pytest.raises(LocationQueryError, match="allow_partial must be boolean"):
        validate_query({
            "query_id": "bad-partial",
            "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
            "allow_partial": "false",
        })


def test_non_wgs84_bbox_crs_fails_closed() -> None:
    with pytest.raises(LocationQueryError, match="requires EPSG:4326/CRS84"):
        validate_query({
            "query_id": "bad-crs",
            "geometry": {
                "type": "bbox",
                "west": -66.1,
                "south": 18.2,
                "east": -65.9,
                "north": 18.4,
                "crs": "EPSG:26920",
            },
        })


def test_invalid_geojson_fails_before_provider_routing() -> None:
    with pytest.raises(LocationQueryError, match="invalid bounded geometry"):
        route_query(
            {
                "query_id": "bad-geojson",
                "geometry": {
                    "type": "geojson",
                    "geojson": {"type": "Polygon", "coordinates": []},
                },
                "families": ["does_not_exist"],
            },
            registry=load_registry(REGISTRY_PATH),
            env={},
        )


def test_out_of_range_geojson_coordinate_fails_closed() -> None:
    with pytest.raises(LocationQueryError, match="invalid bounded geometry"):
        validate_query(
            {
                "query_id": "bad-coordinate",
                "geometry": {
                    "type": "geojson",
                    "geojson": {
                        "type": "Point",
                        "coordinates": [-200.0, 18.0],
                    },
                },
            }
        )


def test_antimeridian_spanning_geojson_fails_until_supported() -> None:
    with pytest.raises(LocationQueryError, match="antimeridian-spanning"):
        validate_query(
            {
                "query_id": "antimeridian",
                "geometry": {
                    "type": "geojson",
                    "geojson": {
                        "type": "MultiPoint",
                        "coordinates": [[179.0, 10.0], [-179.0, 10.0]],
                    },
                },
            }
        )


def test_normalized_query_records_resolved_bbox() -> None:
    normalized = validate_query(
        {
            "query_id": "bbox-record",
            "geometry": {
                "type": "bbox",
                "west": -66.2,
                "south": 18.0,
                "east": -66.0,
                "north": 18.2,
            },
        }
    )
    assert normalized["resolved_bbox_wgs84"] == {
        "west": -66.2,
        "south": 18.0,
        "east": -66.0,
        "north": 18.2,
    }


def test_imagery_fetch_requires_explicit_temporal_for_specialized_execution() -> None:
    plan = route_query(
        {
            "query_id": "imagery-no-time",
            "geometry": {
                "type": "bbox",
                "west": -66.2,
                "south": 18.0,
                "east": -66.0,
                "north": 18.2,
            },
            "families": ["satellite_imagery"],
            "mode": "fetch",
        },
        registry=load_registry(REGISTRY_PATH),
        env={},
    )
    assert "NASA_GIBS_IMAGERY" in plan["execution_gap_provider_ids"]
    assert plan["specialized_execution_blockers"]["NASA_GIBS_IMAGERY"] == "TEMPORAL_REQUIRED"
    assert plan["specialized_call_count"] == 0
    assert plan["fetch_gate"] == "BLOCKED_INCOMPLETE_PROVIDER_EXECUTION"


def test_gibs_temporal_fetch_emits_specialized_call_without_execution_gap() -> None:
    plan = route_query(
        {
            "query_id": "gibs-time",
            "geometry": {
                "type": "bbox",
                "west": -66.2,
                "south": 18.0,
                "east": -66.0,
                "north": 18.2,
            },
            "families": ["satellite_imagery"],
            "temporal": {"date_range": "2026-09-01/2026-09-02"},
            "mode": "fetch",
            "allow_partial": True,
        },
        registry=load_registry(REGISTRY_PATH),
        env={},
    )
    by_id = {row["provider_id"]: row for row in plan["providers"]}
    assert by_id["NASA_GIBS_IMAGERY"]["execution_kind"] == "SPECIALIZED_CALL"
    assert "NASA_GIBS_IMAGERY" in plan["specialized_executor_provider_ids"]
    assert "NASA_GIBS_IMAGERY" not in plan["execution_gap_provider_ids"]
    calls = [row for row in plan["specialized_calls"] if row["provider_id"] == "NASA_GIBS_IMAGERY"]
    assert len(calls) == 1
    assert calls[0]["provider"] == "gibs"
    assert calls[0]["date_range"] == "2026-09-01/2026-09-02"
    assert calls[0]["bbox_wgs84"] == [-66.2, 18.0, -66.0, 18.2]


def test_temporal_range_normalizes_single_date_and_rejects_reverse() -> None:
    normalized = validate_query(
        {
            "query_id": "single-day",
            "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
            "temporal": {"date_range": "2026-09-01"},
        }
    )
    assert normalized["temporal"]["date_range"] == "2026-09-01/2026-09-01"

    with pytest.raises(LocationQueryError, match="end precedes start"):
        validate_query(
            {
                "query_id": "reverse",
                "geometry": {"type": "point", "lat": 18.3, "lon": -66.0},
                "temporal": {"date_range": "2026-09-02/2026-09-01"},
            }
        )
