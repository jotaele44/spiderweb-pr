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


def test_record_entity_carries_location_from_geometry():
    # Z2: Point geometry -> entity location; LineString path -> first-vertex location.
    records = {
        "observations": [{
            "id": "obsgeo01", "source_id": "src_a", "subject_id": "N5854Z",
            "observed_at": "t", "confidence": {"score": 0.78}, "is_synthetic": False,
            "geometry": {"type": "Point", "coordinates": [-66.0918, 18.3373]},
        }],
        "airspace_events": [],
        "tracks": [{
            "id": "trk00001", "source_id": "src_a", "observed_at": "t",
            "confidence": {"score": 0.6}, "is_synthetic": False,
            "path": {"type": "LineString", "coordinates": [[-66.0018, 18.4373], [-66.5632, 18.0083]]},
        }],
    }
    s = build_streams(SOURCES, records, "t")
    obs = next(e for e in s["entities"] if e["entity_type"] == "airspace_observation")
    assert obs["location"] == {"lat": 18.3373, "lon": -66.0918}
    trk = next(e for e in s["entities"] if e["entity_type"] == "airspace_track")
    assert trk["location"] == {"lat": 18.4373, "lon": -66.0018}  # first vertex
    assert all(
        "location" not in e
        for e in s["entities"]
        if e["entity_type"] in ("sensor_source", "aircraft")
    )


def test_record_entity_without_geometry_has_no_location():
    s = build_streams(SOURCES, RECORDS, "t")  # fixture records carry no geometry
    assert all("location" not in e for e in s["entities"])


def test_observation_type_discriminator_maps_to_new_entity_type():
    records = {
        "observations": [{
            "id": "obsusgs1", "source_id": "src_a", "observation_type": "usgs_metallic_occurrence",
            "observed_at": "t", "confidence": {"score": 0.65}, "is_synthetic": False,
            "geometry": {"type": "Point", "coordinates": [-66.46, 18.08]},
        }],
        "airspace_events": [], "tracks": [],
    }
    s = build_streams(SOURCES, records, "t")
    occurrences = [e for e in s["entities"] if e["entity_type"] == "mineral_occurrence"]
    assert len(occurrences) == 1
    assert occurrences[0]["location"] == {"lat": 18.08, "lon": -66.46}
    # no aircraft entity should be minted — this record has no subject_id/callsign.
    assert not any(e["entity_type"] == "aircraft" for e in s["entities"])


def test_unmapped_observation_type_keeps_stream_default():
    # RECORDS' observation row has no observation_type at all -> falls through to
    # RECORD_STREAMS' default, exactly as before this discriminator was added.
    s = build_streams(SOURCES, RECORDS, "t")
    assert any(e["entity_type"] == "airspace_observation" for e in s["entities"])
    assert not any(e["entity_type"] == "mineral_occurrence" for e in s["entities"])


def test_source_kind_discriminator_maps_to_new_entity_type():
    sources_in = [{
        "source_id": "src_layer", "kind": "gis_layer_reference", "is_synthetic": False,
        "confidence": {"score": 0.4}, "first_seen_at": "2026-01-01T00:00:00+00:00",
    }]
    s = build_streams(sources_in, {"observations": [], "airspace_events": [], "tracks": []}, "t")
    assert len(s["entities"]) == 1
    assert s["entities"][0]["entity_type"] == "gis_layer_reference"


def test_unmapped_source_kind_keeps_sensor_source_default():
    # existing SOURCES fixture's kind ("fr24_screenshot") isn't a registered discriminator
    # -> unchanged "sensor_source" default.
    s = build_streams(SOURCES, RECORDS, "t")
    assert any(e["entity_type"] == "sensor_source" for e in s["entities"])
