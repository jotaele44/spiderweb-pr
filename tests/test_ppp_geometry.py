"""Tests for the PPP geometry lane.

The lane resolves a moneysweep-pr concession project's municipality to a real
point from spiderweb's committed reference geographies, then hands it back to the
Hub as an anchored observation. These tests use a synthetic producer package so
they do not depend on a moneysweep-pr sibling checkout being present.
"""

from __future__ import annotations

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


@pytest.fixture
def package(tmp_path):
    def _make(rows):
        pkg = tmp_path / "pkg"
        pkg.mkdir(exist_ok=True)
        (pkg / "entities.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
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
    # Must outrank moneysweep's municipality attribution so a consumer choosing
    # the best available location picks the surveyed point.
    assert row["geometry_confidence"] > row["producer_attribution_confidence"]


def test_accent_folding_matches_either_spelling(package):
    pkg = package([_entity("Luis Munoz Marin Airport", "Carolina")])
    assert pg.resolve_projects(pkg)["resolved_count"] == 1


def test_municipality_mismatch_blocks_a_name_match(package):
    """Both producers must independently agree on the municipality.

    Without this guard a name collision would place a project in the wrong town.
    """
    pkg = package([_entity("Luis Muñoz Marín Airport", "Ponce")])
    out = pg.resolve_projects(pkg)
    assert out["resolved_count"] == 0
    assert out["unresolved_count"] == 1


def test_projects_without_a_municipality_are_not_candidates(package):
    """Island-wide and corridor concessions arrive with no location at all."""
    pkg = package([_entity("LUMA Energy T&D System", None)])
    out = pg.resolve_projects(pkg)
    assert out["producer_projects"] == 0
    assert out["resolved_count"] == 0


def test_non_project_entities_are_ignored(package):
    pkg = package([_entity("Some Agency", "Carolina", entity_type="funding_agency")])
    assert pg.resolve_projects(pkg)["producer_projects"] == 0


def test_unmatched_project_goes_to_the_geocode_queue(package):
    """No committed reference geography means no point — never a guessed one."""
    pkg = package([_entity("Teodoro Moscoso Bridge Concession", "San Juan")])
    out = pg.resolve_projects(pkg)
    assert out["resolved_count"] == 0
    assert out["unresolved"][0]["reason"]


def test_missing_producer_package_degrades_to_empty(tmp_path):
    out = pg.resolve_projects(tmp_path / "absent")
    assert out["resolved_count"] == 0
    assert out["producer_projects"] == 0


# --------------------------------------------------------------------------
# Hub-facing projection
# --------------------------------------------------------------------------


def test_observation_is_anchored_to_an_emitted_entity(package):
    """correlate_observations drops any observation whose anchor is absent from
    the aggregate, so the lane must emit the anchor entity too."""
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    built = fx.build_ppp_geometry_streams(pg.resolve_projects(pkg), NOW)
    assert len(built["observations"]) == 1
    obs = built["observations"][0]
    assert obs["entity_id"] in {e["entity_id"] for e in built["entities"]}


def test_observation_carries_both_point_and_municipality(package):
    """The Hub joins entities to observations on municipality; the point is what
    makes the join worth doing."""
    pkg = package([_entity("Luis Muñoz Marín Airport", "Carolina")])
    obs = fx.build_ppp_geometry_streams(pg.resolve_projects(pkg), NOW)["observations"][0]
    assert obs["location"]["municipality"] == "Carolina"
    assert obs["location"]["lat"] and obs["location"]["lon"]
    assert obs["attributes"]["producer_entity_id"].startswith("ent_")
    assert obs["attributes"]["reference_path"].endswith(".yaml")


def test_lane_cites_its_real_inputs(package):
    """Lineage must name the producer package and reference geography, not the
    envelope streams the rest of the exporter reads."""
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
