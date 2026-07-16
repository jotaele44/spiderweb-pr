"""Contract tests for scripts/build_dataset_catalog_streams.py (USGS + layer-catalog emitter)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_dataset_catalog_streams import (  # noqa: E402
    OUT_FILENAMES,
    build_streams,
    write_streams,
)
from scripts.validate_export import compute_row_id  # noqa: E402


@pytest.fixture(scope="module")
def streams(tmp_path_factory):
    # Empty real_dir: isolates this module's output from build_real_spatial_streams.py's,
    # so counts below are exactly what this emitter produces on its own.
    empty_dir = tmp_path_factory.mktemp("empty_real")
    return build_streams(real_dir=empty_dir)


def test_all_four_streams_present(streams):
    assert set(streams) == {"events", "observations", "tracks", "sources"}
    assert streams["events"] == []
    assert streams["tracks"] == []


def test_expected_counts(streams):
    # 364 real USGS metallic-occurrence points; 1 shared USGS source +
    # 55 WIRED layer-catalog references.
    assert len(streams["observations"]) == 364
    assert len(streams["sources"]) == 56


def test_no_row_is_synthetic(streams):
    for rows in streams.values():
        for row in rows:
            assert row["is_synthetic"] is False


def test_rows_validate_against_stream_schemas(streams):
    jsonschema = pytest.importorskip("jsonschema")
    schema_ids = {"observations": "spiderweb_observation", "sources": "spiderweb_source"}
    for stream, rows in streams.items():
        if stream not in schema_ids:
            continue
        schema = json.loads((REPO_ROOT / "schemas" / f"{schema_ids[stream]}.schema.json").read_text())
        for row in rows:
            jsonschema.validate(row, schema)


def test_row_ids_are_deterministic(streams):
    for rows in streams.values():
        for row in rows:
            assert row["id"] == compute_row_id(row)


def test_usgs_observations_have_real_geometry_and_no_subject_id(streams):
    usgs_obs = [r for r in streams["observations"] if r["observation_type"] == "usgs_metallic_occurrence"]
    assert len(usgs_obs) == 364
    for obs in usgs_obs:
        # A bare subject_id would make federation_export.py mint a spurious "aircraft"
        # entity for every point (a mineral occurrence isn't a tracked subject).
        assert "subject_id" not in obs
        lon, lat = obs["geometry"]["coordinates"]
        # PR + outlying islands (Mona, Desecheo) extent — USGS OFR 98-038 covers all of PR.
        assert 17.5 < lat < 19.0 and -68.0 < lon < -65.0
        assert obs["attributes"]["conversion_status"] == "derived_from_lab_coordinates_attributes_pending"


def test_usgs_observations_reference_one_shared_source(streams):
    usgs_obs = [r for r in streams["observations"] if r["observation_type"] == "usgs_metallic_occurrence"]
    usgs_sources = [r for r in streams["sources"] if r["kind"] == "usgs_ofr_98_038_report"]
    assert len(usgs_sources) == 1
    source_id = usgs_sources[0]["source_id"]
    assert all(obs["source_id"] == source_id for obs in usgs_obs)


def test_layer_catalog_sources_are_low_confidence_with_no_observation(streams):
    layer_sources = [r for r in streams["sources"] if r["kind"] == "gis_layer_reference"]
    assert len(layer_sources) == 55
    for src in layer_sources:
        # T3 evidence_tier -> a documented score under the 0.5 "Low" boundary; these are
        # catalog references, not observed records, and should read that way downstream.
        assert src["confidence"]["score"] < 0.5
        assert src["attributes"]["evidence_tier"] == "T3"
    # no observation stream row should exist for any of these — labels-only, no geometry.
    layer_obs = [r for r in streams["observations"] if r.get("source_id") in {s["source_id"] for s in layer_sources}]
    assert layer_obs == []


def test_merges_with_existing_real_dir(tmp_path):
    pre_existing_obs = {
        "id": "a" * 32, "source_id": "src_x", "subject_id": "N1", "observation_type": "structure_sighting",
        "observed_at": "2026-01-01T00:00:00+00:00", "geometry": {"type": "Point", "coordinates": [-66.0, 18.0]},
        "lineage": [{"step": "s", "actor": "a", "ts": "2026-01-01T00:00:00+00:00"}],
        "confidence": {"score": 0.5, "method": "m"}, "is_synthetic": False,
    }
    pre_existing_src = {
        "id": "b" * 32, "source_id": "src_x", "kind": "manual", "first_seen_at": "2026-01-01T00:00:00+00:00",
        "last_seen_at": "2026-01-01T00:00:00+00:00", "lineage": [{"step": "s", "actor": "a", "ts": "2026-01-01T00:00:00+00:00"}],
        "confidence": {"score": 0.5, "method": "m"}, "is_synthetic": False,
    }
    write_streams(
        {"events": [], "observations": [pre_existing_obs], "tracks": [], "sources": [pre_existing_src]},
        tmp_path,
    )
    merged = build_streams(real_dir=tmp_path)
    assert pre_existing_obs in merged["observations"]
    assert pre_existing_src in merged["sources"]
    assert len(merged["observations"]) == 1 + 364
    assert len(merged["sources"]) == 1 + 56


def test_rerun_against_own_output_is_idempotent(tmp_path):
    """Running build_streams()+write_streams() twice against the SAME real_dir must not
    duplicate this emitter's own rows on the second pass — reproduces and guards against
    the bug where naive concatenation with existing_obs/existing_sources duplicated all
    364 observations + 56 sources on every rerun against an already-merged --real-dir."""
    pre_existing_obs = {
        "id": "c" * 32, "source_id": "src_y", "subject_id": "N2", "observation_type": "airport_reference_location",
        "observed_at": "2026-01-01T00:00:00+00:00", "geometry": {"type": "Point", "coordinates": [-66.5, 18.4]},
        "lineage": [{"step": "s", "actor": "a", "ts": "2026-01-01T00:00:00+00:00"}],
        "confidence": {"score": 0.5, "method": "m"}, "is_synthetic": False,
    }
    pre_existing_src = {
        "id": "d" * 32, "source_id": "src_y", "kind": "manual", "first_seen_at": "2026-01-01T00:00:00+00:00",
        "last_seen_at": "2026-01-01T00:00:00+00:00", "lineage": [{"step": "s", "actor": "a", "ts": "2026-01-01T00:00:00+00:00"}],
        "confidence": {"score": 0.5, "method": "m"}, "is_synthetic": False,
    }
    write_streams(
        {"events": [], "observations": [pre_existing_obs], "tracks": [], "sources": [pre_existing_src]},
        tmp_path,
    )

    first = build_streams(real_dir=tmp_path)
    write_streams(first, tmp_path)

    second = build_streams(real_dir=tmp_path)

    # This emitter's own rows: 364 observations + 56 sources (1 usgs source + 55 layer
    # sources), unchanged and un-duplicated across the rerun.
    assert len(first["observations"]) == 1 + 364
    assert len(first["sources"]) == 1 + 56
    assert len(second["observations"]) == 1 + 364
    assert len(second["sources"]) == 1 + 56

    # The unrelated pre-existing rows (owned by some other emitter) must still be present,
    # exactly once, untouched by either run.
    assert pre_existing_obs in second["observations"]
    assert pre_existing_src in second["sources"]

    # And the content written after run 1 and after run 2 must be byte-identical (true
    # fixed point), not just equal in count.
    write_streams(second, tmp_path)
    for filename in OUT_FILENAMES.values():
        lines = [ln for ln in (tmp_path / filename).read_text().splitlines() if ln.strip()]
        # every row id unique -> no duplication happened in this file
        ids = [json.loads(ln)["id"] for ln in lines]
        assert len(ids) == len(set(ids))


def test_write_streams_emits_package_filenames(streams, tmp_path):
    counts = write_streams(streams, tmp_path)
    for stream, filename in OUT_FILENAMES.items():
        assert (tmp_path / filename).exists()
        lines = [ln for ln in (tmp_path / filename).read_text().splitlines() if ln.strip()]
        assert len(lines) == counts[stream]
