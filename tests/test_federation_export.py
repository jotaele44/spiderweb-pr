import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from federation_export import build_streams  # noqa: E402

SOURCES = [{
    "source_id": "src_a", "kind": "fr24_screenshot", "is_synthetic": False,
    "confidence": {"score": 0.9}, "first_seen_at": "2024-03-15T08:00:00+00:00",
}]
RECORDS = {
    "observations": [{
        "id": "obs1aaaa", "source_id": "src_a", "subject_id": "N5854Z",
        "observed_at": "2024-03-15T08:15:00+00:00", "confidence": {"score": 0.78},
        "is_synthetic": False,
    }],
    "airspace_events": [{
        "id": "ev1bbbb", "source_id": "src_a", "event_time": "2024-03-15T08:00:00+00:00",
        "attributes": {"callsign": "N5854Z"}, "confidence": {"score": 0.81}, "is_synthetic": False,
    }],
    "tracks": [],
}


def test_stream_shapes():
    s = build_streams(SOURCES, RECORDS, "2026-01-01T00:00:00Z")
    types = {e["entity_type"] for e in s["entities"]}
    assert {"sensor_source", "airspace_observation", "airspace_event", "aircraft"} <= types
    assert all(e["entity_id"].startswith("ent_") for e in s["entities"])
    assert all(srow["source_id"].startswith("src_") for srow in s["sources"])
    rels = {r["relationship_type"] for r in s["relationships"]}
    assert {"reported_by", "observed"} <= rels
    assert all(r["relationship_id"].startswith("rel_") for r in s["relationships"])


def test_aircraft_dedup_across_records():
    # both the observation and the event reference N5854Z -> one aircraft entity
    s = build_streams(SOURCES, RECORDS, "t")
    aircraft = [e for e in s["entities"] if e["entity_type"] == "aircraft"]
    assert len(aircraft) == 1


def test_deterministic_ids():
    a = build_streams(SOURCES, RECORDS, "t")
    b = build_streams(SOURCES, RECORDS, "t")
    assert [e["entity_id"] for e in a["entities"]] == [e["entity_id"] for e in b["entities"]]
