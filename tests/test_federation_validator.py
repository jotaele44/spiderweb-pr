"""Fail-closed validation tests for the spiderweb-pr producer package."""
from __future__ import annotations

import json
from pathlib import Path

import federation.validator as validator_module
from federation.export_writer import write_package
from federation.validator import validate_envelope, validate_package
from tests._federation_fixtures import build_spiderweb_streams


def _streams_as_dicts(synthetic=True):
    return {
        name: [r.to_dict() for r in records]
        for name, records in build_spiderweb_streams(synthetic=synthetic).items()
    }


def test_synthetic_package_passes():
    result = validate_package(_streams_as_dicts())
    assert result["valid"], result["errors"]
    assert result["count"] == 4


def test_empty_package_fails_closed():
    assert validate_package({})["valid"] is False
    assert validate_package([])["valid"] is False


def test_gate_has_no_jsonschema_dependency():
    # The existing SchemaValidator no-ops when jsonschema is absent, so the
    # fail-closed gate must NOT route through it. Prove it is pure Python.
    source = Path(validator_module.__file__).read_text(encoding="utf-8")
    assert "import jsonschema" not in source
    assert validate_package([])["valid"] is False
    assert validate_package({"x": [{"producer": "spiderweb-pr"}]})["valid"] is False


def test_unnamespaced_id_fails():
    streams = _streams_as_dicts()
    streams["airspace_events"][0]["record_id"] = "event_abc123"
    result = validate_package(streams)
    assert not result["valid"]
    assert any("namespaced" in e for e in result["errors"])


def test_bad_geo_fails():
    rec = build_spiderweb_streams()["airspace_events"][0].to_dict()
    rec["geo"] = {"type": "Point"}  # missing coordinates
    assert any("geo" in e for e in validate_envelope(rec))


def test_production_mode_rejects_synthetic():
    streams = _streams_as_dicts(synthetic=True)
    assert validate_package(streams, reject_synthetic=True)["valid"] is False
    assert validate_package(streams, reject_synthetic=False)["valid"] is True


def test_written_package_reloads_and_validates(tmp_path):
    manifest = write_package(tmp_path, build_spiderweb_streams(), synthetic=True)
    assert manifest["producer"] == "spiderweb-pr"
    assert manifest["prefix"] == "spiderweb"
    reloaded = {}
    for spec in manifest["files"]:
        stem = spec["filename"].replace(".jsonl", "")
        lines = (tmp_path / spec["filename"]).read_text(encoding="utf-8").splitlines()
        reloaded[stem] = [json.loads(line) for line in lines if line.strip()]
    assert validate_package(reloaded)["valid"]
