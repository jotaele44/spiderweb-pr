from __future__ import annotations

from spiderweb.denominator_chain import (
    build_arcgis_layer_aoi_plan,
    build_usace_service_metadata_plan,
)


def test_usace_service_denominator_emits_only_arcgis_map_feature_metadata() -> None:
    denominator = {
        "schema_version": "spiderweb.arcgis_service_denominator.v1.0",
        "provider_id": "USACE_GENERAL_GIS",
        "state": "PASS",
        "service_count": 3,
        "folder_count": 1,
        "folders": ["Folder"],
        "canonical_records_sha256": "a" * 64,
        "records": [
            {"name_raw": "Port Statistical Area", "type_raw": "FeatureServer"},
            {"name_raw": "Folder/Thing", "type_raw": "MapServer"},
            {"name_raw": "Ignored", "type_raw": "GPServer"},
        ],
    }
    plan = build_usace_service_metadata_plan(
        query={"query_id": "x", "mode": "plan"},
        service_root="https://example.test/arcgis/rest/services",
        denominator=denominator,
    )
    assert plan["request_count"] == 3
    assert all(r["parent_denominator_sha256"] == "a" * 64 for r in plan["requests"])
    assert any("Folder?f=pjson" in r["url"] for r in plan["requests"])
    assert any("Port%20Statistical%20Area/FeatureServer?f=pjson" in r["url"] for r in plan["requests"])
    assert any("Folder/Thing/MapServer?f=pjson" in r["url"] for r in plan["requests"])
    assert plan["policy"]["recursive_folder_discovery_required"] is True


def test_arcgis_layer_denominator_drives_aoi_queries_by_layer_id() -> None:
    denominator = {
        "schema_version": "spiderweb.arcgis_layer_denominator.v1.0",
        "provider_id": "FEMA_PR_ABFE_1PCT",
        "state": "PASS",
        "layer_count": 2,
        "canonical_records_sha256": "b" * 64,
        "records": [
            {"layer_id": 0, "name_raw": "A"},
            {"layer_id": 3, "name_raw": "B"},
        ],
    }
    plan = build_arcgis_layer_aoi_plan(
        query={
            "query_id": "x",
            "geometry": {"type": "bbox", "west": -67.0, "south": 17.8, "east": -65.5, "north": 18.6},
        },
        provider_id="FEMA_PR_ABFE_1PCT",
        service_url="https://example.test/MapServer",
        denominator=denominator,
        role_prefix="abfe",
    )
    assert plan["request_count"] == 2
    assert [r["layer_id"] for r in plan["requests"]] == [0, 3]
    assert all("geometry=" in r["url"] for r in plan["requests"])
    assert all(r["identity_state"] == "SOURCE_LAYER_MANIFESTATION" for r in plan["requests"])
