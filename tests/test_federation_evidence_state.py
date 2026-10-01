"""Additive evidence_state declarations (thehub-pr FEDERATION_EPISTEMIC_STATE_CONTRACT_V1).

Positive: documented record types declare their class and geometry
precision; every emitted declaration validates against the vendored
candidate contract. Negative: a LineString first vertex is never an
observed point, undocumented record types are never classified, and a
callsign-keyed aircraft is never a bound identity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

import scripts.federation_export as fx

REPO = Path(__file__).resolve().parents[1]
VENDORED = REPO / "schemas" / "federation_epistemic_state.v1.schema.json"
# sha256 of thehub-pr schemas/federation/epistemic_state.v1.schema.json (CANDIDATE).
HUB_CANDIDATE_SHA256 = "c31794807d47f00e9ffeb394cf9ddd5d093613dabcf22d4fd81d4a416bade088"
NOW = "2026-01-01T00:00:00Z"
SOURCES = [{"source_id": "src_a", "kind": "gis_layer_reference", "is_synthetic": False, "confidence": {"score": 0.9}}]


def _record(rid, observation_type=None, geometry=None, path=None, subject_id=None):
    record = {"id": rid, "source_id": "src_a", "observed_at": NOW, "confidence": {"score": 0.7}, "is_synthetic": False}
    if observation_type:
        record["observation_type"] = observation_type
    if geometry:
        record["geometry"] = geometry
    if path:
        record["path"] = path
    if subject_id:
        record["subject_id"] = subject_id
    return record


def _entity_for(stream, record):
    streams = fx.build_streams(SOURCES, {"observations": [], "airspace_events": [], "tracks": [], stream: [record]}, NOW)
    record_type = fx.RECORD_STREAMS[stream]
    return next(e for e in streams["entities"] if e["entity_id"] == fx._fid("ent", stream, record["id"])), streams, record_type


def _validator():
    schema = json.loads(VENDORED.read_text())
    wrapper = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/producer_declaration"}
    return jsonschema.Draft202012Validator(wrapper)


POINT = {"type": "Point", "coordinates": [-66.0018, 18.4394]}


def test_vendored_contract_is_byte_identical_to_the_hub_candidate():
    assert hashlib.sha256(VENDORED.read_bytes()).hexdigest() == HUB_CANDIDATE_SHA256


@pytest.mark.parametrize(
    "observation_type, klass, precision, method, observation",
    [
        ("usgs_metallic_occurrence", "CURATED", "OBSERVED_POINT", "AUTHORITATIVE", "OBSERVED_PRESENT"),
        ("airport_reference_location", "CURATED", "REPRESENTATIVE_POINT", "AUTHORITATIVE", None),
        ("structure_sighting", "CURATED", "INTERPRETED_POINT", "INFERRED", "OBSERVED_PRESENT"),
    ],
)
def test_documented_record_types_declare_class_and_precision(observation_type, klass, precision, method, observation):
    entity, _, _ = _entity_for("observations", _record("r1", observation_type, geometry=POINT))
    state = entity["evidence_state"]
    assert (state["epistemic_class"], state["geometry_precision"], state["coordinate_method"]) == (klass, precision, method)
    assert state.get("observation_state") == observation


def test_first_vertex_is_never_an_observed_point():
    path = {"type": "LineString", "coordinates": [[-66.1, 18.4], [-66.2, 18.5]]}
    entity, _, _ = _entity_for("tracks", _record("t1", "usgs_metallic_occurrence", path=path))
    assert entity["location"] == {"lat": 18.4, "lon": -66.1}
    assert entity["evidence_state"]["geometry_precision"] == "REPRESENTATIVE_POINT"
    assert entity["evidence_state"]["coordinate_method"] == "FIRST_VERTEX"


def test_undocumented_record_types_are_not_classified():
    entity, _, _ = _entity_for("observations", _record("o1", "airspace_observation", geometry=POINT))
    state = entity["evidence_state"]
    assert "epistemic_class" not in state
    assert "geometry_precision" not in state
    no_geometry, _, _ = _entity_for("observations", _record("o2", "usgs_metallic_occurrence"))
    assert "geometry_precision" not in no_geometry["evidence_state"]


def test_callsign_keyed_aircraft_is_a_candidate_identity():
    _, streams, _ = _entity_for("airspace_events", _record("e1", subject_id="N5854Z"))
    aircraft = next(e for e in streams["entities"] if e["entity_type"] == "aircraft")
    assert aircraft["evidence_state"]["identity_state"] == "CANDIDATE"
    observed = next(r for r in streams["relationships"] if r["relationship_type"] == "observed")
    assert "epistemic_class" not in observed["evidence_state"]


def test_ppp_resolved_locations_are_computed_representative_points():
    resolution = {"resolved": [{
        "entity_id": "ent_" + "a" * 32, "name": "Airport concession", "lat": 18.4394, "lon": -66.0018,
        "municipality": "Carolina", "reference_path": "configs/airport_registry.yaml", "reference_id": "TJSJ",
        "resolver": "airport_registry", "geometry_confidence": 0.9,
    }]}
    ppp = fx.build_ppp_geometry_streams(resolution, NOW)
    for row in ppp["entities"] + ppp["observations"]:
        assert row["evidence_state"]["epistemic_class"] == "COMPUTED"
        assert row["evidence_state"]["geometry_precision"] == "REPRESENTATIVE_POINT"
    assert ppp["sources"][0]["evidence_state"]["epistemic_class"] == "CURATED"


def test_every_emitted_declaration_is_contract_valid():
    validator = _validator()
    records = {
        "observations": [_record("r1", "usgs_metallic_occurrence", geometry=POINT), _record("r2", subject_id="N1")],
        "airspace_events": [], "tracks": [_record("t1", path={"type": "LineString", "coordinates": [[-66.1, 18.4]]})],
    }
    streams = fx.build_streams(SOURCES, records, NOW)
    rows = [row for stream in ("sources", "entities", "relationships") for row in streams[stream]]
    assert rows and all("evidence_state" in row for row in rows)
    for row in rows:
        assert row["evidence_state"]["contract"] == fx.EVIDENCE_STATE_CONTRACT
        assert list(validator.iter_errors(row["evidence_state"])) == []
        assert row["evidence_state"].get("observation_state") != "OBSERVED_ABSENT"

