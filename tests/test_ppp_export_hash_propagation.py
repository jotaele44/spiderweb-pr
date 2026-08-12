from __future__ import annotations

import hashlib
import json

import scripts.federation_export as fx
from readiness import ppp_geometry as pg

NOW = "2026-01-01T00:00:00Z"


def _package(tmp_path, package_id: str):
    pkg = tmp_path / package_id
    pkg.mkdir()
    entity = {
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
        "created_at": NOW,
        "extracted_at": NOW,
    }
    entities = pkg / "entities.jsonl"
    entities.write_text(json.dumps(entity, sort_keys=True) + "\n")
    digest = hashlib.sha256(entities.read_bytes()).hexdigest()
    manifest = {
        "package_id": package_id,
        "producer": "moneysweep-pr",
        "export_contract_version": "1.0.0",
        "mode": "test",
        "created_at": NOW,
        "extracted_at": NOW,
        "federation": {"producer_repo": "moneysweep-pr", "hub_parent": "thehub-pr"},
        "files": [{
            "filename": "entities.jsonl",
            "stream": "entities",
            "record_count": 1,
            "sha256": digest,
            "schema_id": "federation_entity.schema.json",
        }],
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return pkg


def test_canonical_ppp_rows_serialize_upstream_content_identity(tmp_path):
    pkg = _package(tmp_path, "pkg_" + "1" * 32)
    resolution = pg.resolve_projects(pkg)
    upstream = resolution["producer_package"]
    streams = fx.build_ppp_geometry_streams(resolution, NOW)

    for row in [streams["sources"][0], streams["entities"][0], streams["observations"][0]]:
        lineage = row["lineage"]
        assert lineage["upstream_package"]["package_id"] == upstream["package_id"]
        assert lineage["upstream_package"]["manifest_sha256"] == upstream["manifest_sha256"]
        assert lineage["upstream_package"]["entities_sha256"] == upstream["entities_sha256"]
        assert any(upstream["entities_sha256"] in item for item in lineage["source_inputs"])

    attrs = streams["observations"][0]["attributes"]
    assert attrs["producer_manifest_sha256"] == upstream["manifest_sha256"]
    assert attrs["producer_entities_sha256"] == upstream["entities_sha256"]


def test_upstream_package_identity_changes_downstream_spiderweb_package_id(tmp_path):
    first_resolution = pg.resolve_projects(_package(tmp_path, "pkg_" + "1" * 32))
    second_resolution = pg.resolve_projects(_package(tmp_path, "pkg_" + "2" * 32))

    first_streams = {"sources": [], "entities": [], "relationships": [], "observations": []}
    second_streams = {"sources": [], "entities": [], "relationships": [], "observations": []}
    fx.merge_ppp_geometry(first_streams, fx.build_ppp_geometry_streams(first_resolution, NOW))
    fx.merge_ppp_geometry(second_streams, fx.build_ppp_geometry_streams(second_resolution, NOW))

    first_out = tmp_path / "first-out"
    second_out = tmp_path / "second-out"
    fx.write_package(first_streams, first_out, "test", NOW)
    fx.write_package(second_streams, second_out, "test", NOW)
    first_manifest = json.loads((first_out / "manifest.json").read_text())
    second_manifest = json.loads((second_out / "manifest.json").read_text())
    assert first_manifest["package_id"] != second_manifest["package_id"]
