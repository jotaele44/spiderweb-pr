from __future__ import annotations

import hashlib
import json

import pytest

from spiderweb.provider_denominators import (
    DenominatorError,
    freeze_arcgis_layer_denominator,
    freeze_arcgis_service_denominator,
    freeze_wms_layer_denominator,
    merge_arcgis_service_denominators,
    freeze_arcgis_service_contents_denominator,
    merge_arcgis_service_contents_denominators,
)


def receipt(provider: str, role: str, raw: bytes) -> dict:
    return {
        "provider_id": provider,
        "request_role": role,
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_arcgis_layer_denominator_sorts_and_preserves_names() -> None:
    raw = json.dumps({"layers": [{"id": 50, "name": "Flowline"}, {"id": 20, "name": "Hydrolocation"}]}).encode()
    out = freeze_arcgis_layer_denominator(
        raw=raw,
        receipt=receipt("USGS_3DHP_NHD", "feature_service_metadata", raw),
        provider_id="USGS_3DHP_NHD",
        request_role="feature_service_metadata",
    )
    assert [r["layer_id"] for r in out["records"]] == [20, 50]
    assert out["layer_count"] == 2
    assert out["layer_ids_unique"] is True


def test_arcgis_layer_denominator_rejects_duplicate_id() -> None:
    raw = json.dumps({"layers": [{"id": 1, "name": "A"}, {"id": 1, "name": "B"}]}).encode()
    with pytest.raises(DenominatorError, match="duplicate ArcGIS layer id"):
        freeze_arcgis_layer_denominator(
            raw=raw,
            receipt=receipt("X", "Y", raw),
            provider_id="X",
            request_role="Y",
        )


def test_arcgis_service_denominator_closes_services_and_folders() -> None:
    raw = json.dumps({
        "services": [
            {"name": "B", "type": "FeatureServer"},
            {"name": "A", "type": "MapServer"},
        ],
        "folders": ["z", "a", "a"],
    }).encode()
    out = freeze_arcgis_service_denominator(
        raw=raw,
        receipt=receipt("USACE_GENERAL_GIS", "services_root_denominator", raw),
        provider_id="USACE_GENERAL_GIS",
        request_role="services_root_denominator",
    )
    assert out["service_count"] == 2
    assert out["folders"] == ["a", "z"]
    assert all(row["scope_raw"] == "" for row in out["records"])


def test_wms_denominator_uses_named_layers_only() -> None:
    raw = b"""<WMS_Capabilities><Capability><Layer><Title>root</Title><Layer><Name>FLD_HAZ_AR</Name><Title>Flood Hazard Areas</Title></Layer><Layer><Name>FIRM_PAN</Name><Title>FIRM Panels</Title></Layer></Layer></Capability></WMS_Capabilities>"""
    out = freeze_wms_layer_denominator(
        raw=raw,
        receipt=receipt("FEMA_NFHL", "nfhl_wms_capabilities", raw),
        provider_id="FEMA_NFHL",
        request_role="nfhl_wms_capabilities",
    )
    assert out["layer_count"] == 2
    assert {r["name_raw"] for r in out["records"]} == {"FLD_HAZ_AR", "FIRM_PAN"}


def test_raw_hash_mismatch_fails_closed() -> None:
    raw = b'{"layers":[]}'
    bad = receipt("X", "Y", raw)
    bad["sha256"] = "0" * 64
    with pytest.raises(DenominatorError, match="SHA256"):
        freeze_arcgis_layer_denominator(raw=raw, receipt=bad, provider_id="X", request_role="Y")


def test_merge_arcgis_service_denominators_preserves_folder_scope() -> None:
    root = {
        "schema_version": "spiderweb.arcgis_service_denominator.v1.0",
        "provider_id": "USACE_GENERAL_GIS",
        "state": "PASS",
        "canonical_records_sha256": "1" * 64,
        "folders": ["Navigation"],
        "records": [{"scope_raw": "", "name_raw": "Ports", "type_raw": "FeatureServer"}],
    }
    folder = {
        "schema_version": "spiderweb.arcgis_service_denominator.v1.0",
        "provider_id": "USACE_GENERAL_GIS",
        "state": "PASS",
        "canonical_records_sha256": "2" * 64,
        "folders": [],
        "records": [{"scope_raw": "Navigation", "name_raw": "Ports", "type_raw": "FeatureServer"}],
    }
    out = merge_arcgis_service_denominators([root, folder], provider_id="USACE_GENERAL_GIS")
    assert out["service_count"] == 2
    assert {(r["scope_raw"], r["name_raw"]) for r in out["records"]} == {
        ("", "Ports"),
        ("Navigation", "Ports"),
    }


def test_merge_rejects_duplicate_scoped_service() -> None:
    row = {
        "schema_version": "spiderweb.arcgis_service_denominator.v1.0",
        "provider_id": "USACE_GENERAL_GIS",
        "state": "PASS",
        "canonical_records_sha256": "3" * 64,
        "folders": [],
        "records": [{"scope_raw": "", "name_raw": "Ports", "type_raw": "FeatureServer"}],
    }
    with pytest.raises(DenominatorError, match="duplicate service across denominators"):
        merge_arcgis_service_denominators([row, row], provider_id="USACE_GENERAL_GIS")


def test_service_contents_preserve_layers_tables_and_service_binding() -> None:
    raw = json.dumps({
        "layers": [{"id": 0, "name": "Ports"}],
        "tables": [{"id": 7, "name": "Statistics"}],
    }).encode()
    receipt_row = receipt("USACE_GENERAL_GIS", "service_metadata:Navigation:Waterways:FeatureServer", raw)
    receipt_row["source_binding"] = {
        "service_scope_raw": "Navigation",
        "service_name_raw": "Waterways",
        "service_type_raw": "FeatureServer",
    }
    out = freeze_arcgis_service_contents_denominator(
        raw=raw,
        receipt=receipt_row,
        provider_id="USACE_GENERAL_GIS",
        request_role="service_metadata:Navigation:Waterways:FeatureServer",
    )
    assert out["layer_count"] == 1
    assert out["table_count"] == 1
    assert out["service_scope_raw"] == "Navigation"
    assert {(row["kind"], row["id"]) for row in out["records"]} == {("layer", 0), ("table", 7)}


def test_service_contents_merge_keeps_same_id_in_different_services_distinct() -> None:
    a = {
        "schema_version": "spiderweb.arcgis_service_contents_denominator.v1.0",
        "provider_id": "USACE_GENERAL_GIS",
        "state": "PASS",
        "canonical_records_sha256": "a" * 64,
        "service_scope_raw": "",
        "service_name_raw": "Ports",
        "service_type_raw": "FeatureServer",
        "records": [{"kind": "layer", "id": 0, "name_raw": "Ports"}],
    }
    b = {
        "schema_version": "spiderweb.arcgis_service_contents_denominator.v1.0",
        "provider_id": "USACE_GENERAL_GIS",
        "state": "PASS",
        "canonical_records_sha256": "b" * 64,
        "service_scope_raw": "Navigation",
        "service_name_raw": "Ports",
        "service_type_raw": "FeatureServer",
        "records": [{"kind": "layer", "id": 0, "name_raw": "Ports"}],
    }
    out = merge_arcgis_service_contents_denominators([a, b], provider_id="USACE_GENERAL_GIS")
    assert out["record_count"] == 2
    assert out["layer_count"] == 2
    assert {
        (row["service_scope_raw"], row["service_name_raw"], row["kind"], row["id"])
        for row in out["records"]
    } == {
        ("", "Ports", "layer", 0),
        ("Navigation", "Ports", "layer", 0),
    }
