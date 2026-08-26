from __future__ import annotations

import json
from pathlib import Path

import pytest

from spiderweb.subsurface.preflight import freeze_arcgis_layer_manifest
from spiderweb.subsurface.sources import SourceKind, SourceSpec, SourceStatus


def spec() -> SourceSpec:
    return SourceSpec(
        "FIX", "GEOLOGY_KARST_CAVES", "fixture", "fixture",
        SourceKind.ARCGIS_LAYER, "https://example.test/MapServer",
        SourceStatus.VERIFIED_QUERYABLE, layer_id=3,
    )


def test_preflight_freezes_schema_oid_and_query_contract(tmp_path: Path):
    payload = {
        "name": "Geologia",
        "geometryType": "esriGeometryPolygon",
        "objectIdField": "OBJECTID",
        "maxRecordCount": 1000,
        "hasZ": False,
        "hasM": False,
        "supportedQueryFormats": "JSON, geoJSON, PBF",
        "extent": {"spatialReference": {"wkid": 32161}},
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "UNIT", "type": "esriFieldTypeString"},
        ],
    }

    def fetch(url: str) -> bytes:
        assert url.endswith("/3?f=json")
        return json.dumps(payload).encode()

    manifest = freeze_arcgis_layer_manifest(spec(), fetch=fetch, snapshot_dir=tmp_path)
    assert manifest.object_id_field == "OBJECTID"
    assert manifest.max_record_count == 1000
    assert manifest.spatial_reference == {"wkid": 32161}
    assert len(manifest.fields) == 2
    assert len(manifest.byte_sha256) == 64
    assert len(manifest.logical_sha256) == 64
    assert (tmp_path / "FIX" / "layer_metadata.raw.json").read_bytes()
    contract = json.loads((tmp_path / "FIX" / "query_contract.json").read_text())
    assert contract["count_preflight"] is True
    assert contract["orderByFields"] == "OBJECTID ASC"


def test_preflight_discovers_oid_from_fields_when_property_absent():
    payload = {
        "name": "x",
        "fields": [{"name": "FID", "type": "esriFieldTypeOID"}],
        "supportedQueryFormats": "JSON, geoJSON",
    }
    manifest = freeze_arcgis_layer_manifest(
        spec(), fetch=lambda _url: json.dumps(payload).encode()
    )
    assert manifest.object_id_field == "FID"


def test_preflight_missing_oid_fails_closed():
    payload = {"name": "x", "fields": [], "supportedQueryFormats": "JSON"}
    with pytest.raises(RuntimeError, match="no OID"):
        freeze_arcgis_layer_manifest(
            spec(), fetch=lambda _url: json.dumps(payload).encode()
        )


def test_preflight_service_error_fails_not_zero():
    with pytest.raises(RuntimeError, match="metadata query failed"):
        freeze_arcgis_layer_manifest(
            spec(), fetch=lambda _url: b'{"error":{"code":500}}'
        )
