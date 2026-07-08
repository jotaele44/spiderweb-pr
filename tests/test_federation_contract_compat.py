"""Phase 3 — federation canonical-export contract-compat test (T9-74).

Pins the hub-facing contract produced by ``scripts/federation_export.py``: the
``build_streams`` record shapes, the export contract version, and the
deterministic ``package_id``. A producer-side change that alters any of these
breaks this test, preventing a silent break of thehub-pr's consumer.

The golden fixture is generated from exactly the ``_fixed_input()`` below (with
``FIXED_NOW``); regenerate it by running ``build_streams``/``write_package`` on
that input if the canonical contract intentionally changes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.federation_export as fx

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "fixtures" / "federation_canonical.golden.json"

FIXED_NOW = "2023-03-20T00:00:00Z"
MODE = "test"

EXPECTED_MANIFEST_KEYS = {
    "package_id", "producer", "export_contract_version", "mode",
    "created_at", "extracted_at", "federation", "files",
}


def _fixed_input():
    sources_in = [
        {"source_id": "src_a", "kind": "fr24", "confidence": 1.0,
         "is_synthetic": True, "first_seen_at": "2023-03-20T00:00:00Z"},
    ]
    records = {
        "airspace_events": [
            {"id": "evt_00000001", "source_id": "src_a",
             "observed_at": "2023-03-20T12:00:00Z", "confidence": 0.8,
             "geometry": {"type": "Point", "coordinates": [-66.1057, 18.4655]},
             "subject_id": "N12345"},
        ],
        "observations": [
            {"id": "obs_00000001", "source_id": "src_a",
             "observed_at": "2023-03-20T12:05:00Z", "confidence": 0.7,
             "geometry": {"type": "Point", "coordinates": [-66.0, 18.4]}},
        ],
        "tracks": [
            {"id": "trk_00000001", "source_id": "src_a",
             "observed_at": "2023-03-20T12:10:00Z", "confidence": 0.9,
             "path": {"type": "LineString",
                      "coordinates": [[-66.2, 18.3], [-66.3, 18.2]]}},
        ],
    }
    return sources_in, records


def _build():
    sources_in, records = _fixed_input()
    return fx.build_streams(sources_in, records, FIXED_NOW)


def _golden():
    return json.loads(GOLDEN.read_text())


def test_contract_version_pinned():
    assert fx.CONTRACT_VERSION == "1.0.0"
    assert _golden()["manifest"]["export_contract_version"] == "1.0.0"


def test_build_streams_matches_golden():
    # Pins record key-sets, deterministic sha256 IDs, and the Z2 location projection.
    assert _build() == _golden()["streams"]


def test_manifest_is_deterministic(tmp_path):
    streams = _build()
    mpath = fx.write_package(streams, tmp_path / "out", MODE, FIXED_NOW)
    manifest = json.loads(Path(mpath).read_text())
    assert manifest == _golden()["manifest"]
    assert set(manifest) == EXPECTED_MANIFEST_KEYS
    assert manifest["package_id"].startswith("pkg_")


def test_package_id_is_stable_across_two_builds(tmp_path):
    streams = _build()
    m1 = json.loads(Path(fx.write_package(streams, tmp_path / "a", MODE, FIXED_NOW)).read_text())
    m2 = json.loads(Path(fx.write_package(streams, tmp_path / "b", MODE, FIXED_NOW)).read_text())
    assert m1["package_id"] == m2["package_id"]


def test_streams_validate_against_canonical_schemas():
    pytest.importorskip("jsonschema")
    from integration.schema_validation import SchemaValidator

    v = SchemaValidator()
    schema_for = {
        "sources": "federation_source",
        "entities": "federation_entity",
        "relationships": "federation_relationship",
    }
    streams = _build()
    for stream, schema_id in schema_for.items():
        assert schema_id in v.available_schemas(), f"{schema_id} not loaded"
        for rec in streams[stream]:
            result = v.validate(rec, schema_id)
            assert result["valid"], f"{stream} record invalid: {result['errors']}\n{rec}"


def test_manifest_schema_ids_resolve_to_real_schemas():
    # Each manifest file's schema_id must resolve to a registered schema
    # (previously these federation_{source,entity,relationship} ids were dangling).
    pytest.importorskip("jsonschema")
    from integration.schema_validation import SchemaValidator

    v = SchemaValidator()
    for f in _golden()["manifest"]["files"]:
        stem = f["schema_id"].replace(".schema.json", "")
        assert stem in v.available_schemas(), f"dangling schema_id: {f['schema_id']}"


def test_manifest_validates_against_canonical_manifest_schema():
    # write_package()'s own manifest envelope must validate against
    # schemas/federation_export_manifest.schema.json — this is the Hub-facing
    # contract, distinct from federation/export_writer.py's legacy manifest
    # shape (a different producer-side module, out of scope here).
    pytest.importorskip("jsonschema")
    from integration.schema_validation import SchemaValidator

    v = SchemaValidator()
    assert "federation_export_manifest" in v.available_schemas()
    result = v.validate(_golden()["manifest"], "federation_export_manifest")
    assert result["valid"], f"manifest invalid: {result['errors']}"
