"""Envelope contract-version assertion tests (ROI #10: JSON Schema + explicit
version assertion for federation/envelope.py).

CONTRACT_VERSION already existed as a constant with a comment pointing at
federation/validator.py for the assertion — but nothing there ever checked it,
and no envelope or manifest ever carried it. This closes that gap: the package
manifest (not each individual envelope — consistent with how
scripts/federation_export.py's separate, already-tested contract carries its
own export_contract_version at the manifest level) now stamps contract_version,
and validate_package()/validate_manifest_contract_version() assert it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from federation.envelope import CONTRACT_VERSION
from federation.validator import validate_manifest_contract_version, validate_package
from tests._federation_fixtures import build_spiderweb_streams, write_spiderweb_package


def _streams_as_dicts():
    return {
        name: [r.to_dict() for r in records]
        for name, records in build_spiderweb_streams().items()
    }


def test_written_manifest_carries_contract_version(tmp_path):
    manifest = write_spiderweb_package(tmp_path)
    assert manifest["contract_version"] == CONTRACT_VERSION == "1.0"


def test_manifest_version_check_accepts_matching_version():
    manifest = {"contract_version": CONTRACT_VERSION}
    assert validate_manifest_contract_version(manifest) == []


def test_manifest_version_check_accepts_absent_version_as_legacy():
    # Ratchet, not retroactive: a manifest predating this check must not start failing.
    assert validate_manifest_contract_version({}) == []
    assert validate_manifest_contract_version({"producer": "spiderweb-pr"}) == []


def test_manifest_version_check_fails_closed_on_mismatch():
    errors = validate_manifest_contract_version({"contract_version": "0.9"})
    assert len(errors) == 1
    assert "0.9" in errors[0] and CONTRACT_VERSION in errors[0]


def test_validate_package_folds_in_manifest_version_check():
    streams = _streams_as_dicts()
    ok = validate_package(streams, manifest={"contract_version": CONTRACT_VERSION})
    assert ok["valid"], ok["errors"]

    legacy = validate_package(streams, manifest={})
    assert legacy["valid"], legacy["errors"]

    bad = validate_package(streams, manifest={"contract_version": "2.0"})
    assert not bad["valid"]
    assert any("contract_version mismatch" in e for e in bad["errors"])


def test_written_package_reloads_with_version_checked(tmp_path):
    """End-to-end: write a real package, reload it, validate streams AND the
    manifest's contract_version together — mirrors the pre-existing
    test_written_package_reloads_and_validates but exercises the new check."""
    manifest = write_spiderweb_package(tmp_path)
    reloaded = {}
    for spec in manifest["files"]:
        stem = spec["filename"].replace(".jsonl", "")
        lines = (tmp_path / spec["filename"]).read_text(encoding="utf-8").splitlines()
        reloaded[stem] = [json.loads(line) for line in lines if line.strip()]
    result = validate_package(reloaded, manifest=manifest)
    assert result["valid"], result["errors"]


def test_envelope_schema_validates_real_envelopes():
    pytest.importorskip("jsonschema")
    from integration.schema_validation import SchemaValidator

    v = SchemaValidator()
    assert "federation_envelope" in v.available_schemas()
    for records in _streams_as_dicts().values():
        for rec in records:
            result = v.validate(rec, "federation_envelope")
            label = rec.get("record_type")
            assert result["valid"], f"{label} invalid: {result['errors']}\n{rec}"


def test_envelope_schema_rejects_bad_confidence_score():
    pytest.importorskip("jsonschema")
    from integration.schema_validation import SchemaValidator

    v = SchemaValidator()
    rec = _streams_as_dicts()["observations"][0]
    rec["confidence"]["score"] = 1.5  # out of [0, 1]
    result = v.validate(rec, "federation_envelope")
    assert not result["valid"]


def test_envelope_schema_file_is_valid_json():
    schemas_dir = Path(__file__).resolve().parents[1] / "schemas"
    path = schemas_dir / "federation_envelope.schema.json"
    schema = json.loads(path.read_text())
    assert schema["$id"] == "federation_envelope"
