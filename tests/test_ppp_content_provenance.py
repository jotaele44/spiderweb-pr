from __future__ import annotations

import hashlib
import json

from readiness import ppp_geometry as pg


def _write_package(tmp_path):
    package = tmp_path / "moneysweep"
    package.mkdir()
    row = {
        "entity_id": "ent_" + "a" * 32,
        "source_id": "src_" + "b" * 32,
        "name": "Luis Muñoz Marín Airport",
        "normalized_name": "LUIS MUNOZ MARIN AIRPORT",
        "entity_type": "project",
        "jurisdiction": "PR",
        "location": {"municipality": "Carolina", "attribution_confidence": 0.7},
        "confidence": 0.8,
        "lineage": {"producer_script": "fixture", "producer_phase": "TEST", "source_inputs": []},
        "synthetic": False,
        "created_at": "2026-01-01T00:00:00Z",
        "extracted_at": "2026-01-01T00:00:00Z",
    }
    entities = package / "entities.jsonl"
    entities.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    entity_sha = hashlib.sha256(entities.read_bytes()).hexdigest()
    manifest = {
        "package_id": "pkg_" + "c" * 32,
        "producer": "moneysweep-pr",
        "export_contract_version": "1.0.0",
        "mode": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "extracted_at": "2026-01-01T00:00:00Z",
        "federation": {"producer_repo": "moneysweep-pr", "hub_parent": "thehub-pr"},
        "files": [{
            "filename": "entities.jsonl",
            "stream": "entities",
            "record_count": 1,
            "sha256": entity_sha,
            "schema_id": "federation_entity.schema.json",
        }],
    }
    manifest_path = package / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return package, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), entity_sha


def test_every_resolved_ppp_row_carries_content_addressed_input_identity(tmp_path):
    package, manifest_sha, entity_sha = _write_package(tmp_path)
    result = pg.resolve_projects(package)
    assert result["resolved_count"] == 1
    row = result["resolved"][0]
    assert row["producer_package_id"] == "pkg_" + "c" * 32
    assert row["producer_manifest_sha256"] == manifest_sha
    assert row["producer_entities_sha256"] == entity_sha
    assert row["producer_entities_filename"] == "entities.jsonl"
    assert row["producer_entities_record_count"] == 1


def test_unresolved_rows_retain_same_upstream_package_identity(tmp_path):
    package, manifest_sha, entity_sha = _write_package(tmp_path)
    entities = package / "entities.jsonl"
    row = json.loads(entities.read_text())
    row["name"] = "No Matching Facility"
    row["normalized_name"] = "NO MATCHING FACILITY"
    entities.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    entity_sha = hashlib.sha256(entities.read_bytes()).hexdigest()
    manifest = json.loads((package / "manifest.json").read_text())
    manifest["files"][0]["sha256"] = entity_sha
    (package / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    manifest_sha = hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()

    result = pg.resolve_projects(package)
    assert result["unresolved_count"] == 1
    unresolved = result["unresolved"][0]
    assert unresolved["producer_manifest_sha256"] == manifest_sha
    assert unresolved["producer_entities_sha256"] == entity_sha
