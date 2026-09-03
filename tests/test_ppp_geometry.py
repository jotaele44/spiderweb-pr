"""Tests for the PPP geometry lane.

The lane resolves a moneysweep-pr concession project's municipality to a real
point from spiderweb's committed reference geographies, then hands it back to the
Hub as an anchored observation. Test packages are content-addressed synthetic
Moneysweep exports, so no sibling checkout is required.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import scripts.federation_export as fx
from readiness import ppp_geometry as pg

NOW = "2026-01-01T00:00:00Z"


def _entity(name, municipality, entity_type="project", eid="ent_" + "a" * 32):
    row = {
        "entity_id": eid,
        "source_id": "src_" + "b" * 32,
        "name": name,
        "normalized_name": name.upper(),
        "entity_type": entity_type,
        "jurisdiction": "PR",
        "confidence": 0.85,
        "lineage": {"producer_script": "p", "producer_phase": "q", "source_inputs": []},
        "synthetic": False,
        "created_at": NOW,
        "extracted_at": NOW,
    }
    if municipality:
        row["location"] = {
            "municipality": municipality,
            "attribution_source": "data/canonical_v1/projects.csv#municipality_id",
            "attribution_confidence": 0.7,
        }
    return row


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def package(tmp_path):
    def _make(rows, *, producer="moneysweep-pr"):
        pkg = tmp_path / "pkg"
        pkg.mkdir(exist_ok=True)
        entities = pkg / "entities.jsonl"
        entities.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
        )
        manifest = {
            "package_id": "pkg_test_content_addressed",
            "producer": producer,
            "files": [{
                "filename": "entities.jsonl",
                "stream": "entities",
                "record_count": len(rows),
                "sha256": _sha(entities),
                "schema_id": "federation_entity.schema.json",
            }],
        }
        (pkg / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return pkg

    return _make


def test_resolves_airport_from_committed_registry(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    out = pg.resolve_projects(pkg)
    assert out["resolved_count"] == 1
    row = out["resolved"][0]
    assert row["resolver"] == "airport_registry"
    assert row["municipality"] == "Carolina"
    assert (round(row["lat"], 3), round(row["lon"], 3)) == (18.439, -66.002)
    assert row["geometry_confidence"] > row["producer_attribution_confidence"]
    assert row["producer_package_id"] == "pkg_test_content_addressed"
    assert row["producer_entities_sha256"] == out["producer_package"]["entities_sha256"]


def test_accent_folding_matches_either_spelling(package):
    pkg = package([_entity("Luis Munoz Marin Airport", "Carolina")])
    assert pg.resolve_projects(pkg)["resolved_count"] == 1


def test_municipality_mismatch_blocks_a_name_match(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Ponce")])
    out = pg.resolve_projects(pkg)
    assert out["resolved_count"] == 0
    assert out["unresolved_count"] == 1


def test_projects_without_a_municipality_are_not_candidates(package):
    pkg = package([_entity("LUMA Energy T&D System", None)])
    out = pg.resolve_projects(pkg)
    assert out["producer_projects"] == 0
    assert out["resolved_count"] == 0


def test_non_project_entities_are_ignored(package):
    pkg = package([_entity("Some Agency", "Carolina", entity_type="funding_agency")])
    assert pg.resolve_projects(pkg)["producer_projects"] == 0


def test_unmatched_project_goes_to_the_geocode_queue(package):
    pkg = package([_entity("Teodoro Moscoso Bridge Concession", "San Juan")])
    out = pg.resolve_projects(pkg)
    assert out["resolved_count"] == 0
    assert out["unresolved"][0]["reason"]


def test_missing_or_implicit_producer_package_fails_closed(tmp_path):
    with pytest.raises(pg.PPPGeometryError, match="explicit moneysweep export package required"):
        pg.resolve_projects()
    with pytest.raises(pg.PPPGeometryError, match="missing moneysweep manifest"):
        pg.resolve_projects(tmp_path / "absent")


def test_wrong_producer_identity_fails_closed(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")], producer="other-pr")
    with pytest.raises(pg.PPPGeometryError, match="unexpected producer identity"):
        pg.resolve_projects(pkg)


def test_entities_hash_mismatch_fails_closed(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    with (pkg / "entities.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_entity("Tampered", "Ponce", eid="ent_" + "c" * 32)) + "\n")
    with pytest.raises(pg.PPPGeometryError, match="sha256 mismatch"):
        pg.resolve_projects(pkg)


def test_entities_record_count_mismatch_fails_closed(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    manifest_path = pkg / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["record_count"] = 999
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    with pytest.raises(pg.PPPGeometryError, match="record_count mismatch"):
        pg.resolve_projects(pkg)


def test_verified_package_metadata_is_content_addressed(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    meta = pg.verify_moneysweep_package(pkg)
    assert meta["producer"] == "moneysweep-pr"
    assert meta["package_id"] == "pkg_test_content_addressed"
    assert meta["entities_sha256"] == _sha(pkg / "entities.jsonl")
    assert meta["manifest_sha256"] == _sha(pkg / "manifest.json")
    assert meta["entities_record_count"] == 1


# --------------------------------------------------------------------------
# Hub-facing projection
# --------------------------------------------------------------------------


def test_observation_is_anchored_to_an_emitted_entity(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    built = fx.build_ppp_geometry_streams(pg.resolve_projects(pkg), NOW)
    assert len(built["observations"]) == 1
    obs = built["observations"][0]
    assert obs["entity_id"] in {e["entity_id"] for e in built["entities"]}


def test_observation_carries_both_point_and_municipality(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    obs = fx.build_ppp_geometry_streams(pg.resolve_projects(pkg), NOW)["observations"][0]
    assert obs["location"]["municipality"] == "Carolina"
    assert obs["location"]["lat"] and obs["location"]["lon"]
    assert obs["attributes"]["producer_entity_id"].startswith("ent_")
    assert obs["attributes"]["reference_path"].endswith(".yaml")


def test_lane_cites_its_real_inputs(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    obs = fx.build_ppp_geometry_streams(pg.resolve_projects(pkg), NOW)["observations"][0]
    inputs = obs["lineage"]["source_inputs"]
    assert any("moneysweep" in i for i in inputs)
    assert any("airport_registry" in i for i in inputs)
    assert obs["lineage"]["extraction_method"] == "reference_geography_resolution"


def test_empty_resolution_emits_nothing():
    built = fx.build_ppp_geometry_streams({"resolved": []}, NOW)
    assert built == {"sources": [], "entities": [], "observations": []}


def test_merge_is_idempotent_on_sources_and_entities(package):
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    ppp = fx.build_ppp_geometry_streams(pg.resolve_projects(pkg), NOW)
    streams = {"sources": [], "entities": [], "relationships": [], "observations": []}
    fx.merge_ppp_geometry(streams, ppp)
    fx.merge_ppp_geometry(streams, ppp)
    assert len(streams["sources"]) == 1
    assert len(streams["entities"]) == 1
