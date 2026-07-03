"""Contract tests for scripts/build_real_spatial_streams.py (real-row emitter)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_real_spatial_streams import (  # noqa: E402
    OUT_FILENAMES,
    build_streams,
    write_streams,
)
from scripts.validate_export import compute_row_id  # noqa: E402

AS_OF = "2026-06-13T14:47:30-04:00"


@pytest.fixture(scope="module")
def streams():
    return build_streams(registry_as_of=AS_OF)


def test_all_four_streams_present(streams):
    assert set(streams) == {"events", "observations", "tracks", "sources"}
    assert streams["observations"], "must emit at least one real observation"
    assert streams["sources"], "must emit at least one real source"
    # no real event/track data exists in-repo; these must stay empty, not faked
    assert streams["events"] == []
    assert streams["tracks"] == []


def test_no_row_is_synthetic(streams):
    for rows in streams.values():
        for row in rows:
            assert row["is_synthetic"] is False


def test_rows_validate_against_stream_schemas(streams):
    jsonschema = pytest.importorskip("jsonschema")
    schema_ids = {
        "events": "spiderweb_event",
        "observations": "spiderweb_observation",
        "tracks": "spiderweb_track",
        "sources": "spiderweb_source",
    }
    for stream, rows in streams.items():
        schema = json.loads(
            (REPO_ROOT / "schemas" / f"{schema_ids[stream]}.schema.json").read_text()
        )
        for row in rows:
            jsonschema.validate(row, schema)


def test_row_ids_are_deterministic(streams):
    for rows in streams.values():
        for row in rows:
            assert row["id"] == compute_row_id(row)


def test_site_observation_carries_real_capture(streams):
    site_obs = [
        r for r in streams["observations"] if r["observation_type"] == "structure_sighting"
    ]
    assert len(site_obs) == 1
    obs = site_obs[0]
    assert obs["subject_id"] == "SITE_RI_20260522_001"
    lon, lat = obs["geometry"]["coordinates"]
    assert 17.9 < lat < 18.6 and -67.3 < lon < -65.2  # PR extent
    assert obs["confidence"]["method"] == "human_review"
    assert any(step["step"] == "human_review" for step in obs["lineage"])


def test_airport_observations_reference_registry_source(streams):
    airport_obs = [
        r
        for r in streams["observations"]
        if r["observation_type"] == "airport_reference_location"
    ]
    assert airport_obs, "airport registry must produce reference observations"
    registry_sources = [r for r in streams["sources"] if r["kind"] == "reference_registry"]
    assert len(registry_sources) == 1
    source_id = registry_sources[0]["source_id"]
    for obs in airport_obs:
        assert obs["source_id"] == source_id
        lon, lat = obs["geometry"]["coordinates"]
        assert 17.9 < lat < 18.6 and -67.4 < lon < -65.2


def test_write_streams_emits_package_filenames(streams, tmp_path):
    counts = write_streams(streams, tmp_path)
    for stream, filename in OUT_FILENAMES.items():
        assert (tmp_path / filename).exists()
        lines = [
            ln for ln in (tmp_path / filename).read_text().splitlines() if ln.strip()
        ]
        assert len(lines) == counts[stream]
