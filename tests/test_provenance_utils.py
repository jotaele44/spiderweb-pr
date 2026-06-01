"""Tests for provenance_utils — reproducibility metadata, sha256, GeoJSON summary."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from provenance_utils import (  # noqa: E402
    REPRO_KEYS,
    attach_to_manifest,
    compute_sha256,
    feature_collection_summary,
    git_head_or_unknown,
    reproducibility_metadata,
)


# ── reproducibility_metadata ────────────────────────────────────────────────


def test_reproducibility_metadata_has_all_eight_keys():
    md = reproducibility_metadata(command="test", input_paths=[])
    for k in REPRO_KEYS:
        assert k in md, f"missing reproducibility key: {k}"
    assert len(REPRO_KEYS) == 8


def test_reproducibility_metadata_mode_propagates():
    assert reproducibility_metadata(mode="strict")["mode"] == "strict"
    assert reproducibility_metadata(mode="demo")["mode"] == "demo"
    assert reproducibility_metadata()["mode"] == "normal"


def test_reproducibility_metadata_hashes_inputs(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"hello\n")
    md = reproducibility_metadata(input_paths=[str(p)])
    assert str(p) in md["input_sha256s"]
    expected = hashlib.sha256(b"hello\n").hexdigest()
    assert md["input_sha256s"][str(p)] == expected


def test_reproducibility_metadata_skips_large_files(tmp_path):
    p = tmp_path / "big.bin"
    p.write_bytes(b"\x00" * 1024)
    md = reproducibility_metadata(input_paths=[str(p)], hash_max_bytes=512)
    assert md["input_sha256s"][str(p)] == "skipped_large_file"


def test_reproducibility_metadata_unknown_for_missing(tmp_path):
    md = reproducibility_metadata(input_paths=[str(tmp_path / "nope.txt")])
    assert md["input_sha256s"][str(tmp_path / "nope.txt")] == "unknown"


# ── compute_sha256 ──────────────────────────────────────────────────────────


def test_compute_sha256_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    payload = b"the quick brown fox" * 1024
    p.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert compute_sha256(str(p)) == expected


def test_compute_sha256_missing_returns_unknown(tmp_path):
    assert compute_sha256(str(tmp_path / "nope")) == "unknown"


def test_compute_sha256_oversized_returns_sentinel(tmp_path):
    p = tmp_path / "big.bin"
    p.write_bytes(b"x" * 100)
    assert compute_sha256(str(p), max_bytes=10) == "skipped_large_file"


# ── git_head_or_unknown ─────────────────────────────────────────────────────


def test_git_head_or_unknown_never_raises():
    """Contract: returns a string, never raises (Open Risk #2)."""
    result = git_head_or_unknown()
    assert isinstance(result, str)
    # Either a full 40-char SHA, a short sha, or the explicit "unknown" sentinel
    assert result == "unknown" or re.fullmatch(r"[0-9a-f]{7,40}", result)


# ── attach_to_manifest ──────────────────────────────────────────────────────


def test_attach_to_manifest_returns_same_dict():
    manifest = {"files": []}
    out = attach_to_manifest(manifest, command="x")
    assert out is manifest
    assert "reproducibility" in manifest
    for k in REPRO_KEYS:
        assert k in manifest["reproducibility"]


# ── feature_collection_summary ──────────────────────────────────────────────


def test_feature_collection_summary_empty():
    s = feature_collection_summary([])
    assert s["feature_count"] == 0
    assert s["bbox"] is None
    assert s["centroid"] is None
    assert s["crs"] == "EPSG:4326"
    assert s["geometry_types"] == []


def test_feature_collection_summary_points():
    features = [
        {"geometry": {"type": "Point", "coordinates": [-66.0, 18.0]}},
        {"geometry": {"type": "Point", "coordinates": [-67.0, 19.0]}},
    ]
    s = feature_collection_summary(features)
    assert s["feature_count"] == 2
    assert s["bbox"] == [-67.0, 18.0, -66.0, 19.0]
    assert s["centroid"] == [-66.5, 18.5]
    assert "Point" in s["geometry_types"]


def test_feature_collection_summary_linestring():
    features = [{"geometry": {"type": "LineString",
                              "coordinates": [[-67.0, 18.0], [-66.0, 19.0]]}}]
    s = feature_collection_summary(features)
    assert s["feature_count"] == 1
    assert s["bbox"] == [-67.0, 18.0, -66.0, 19.0]
    assert "LineString" in s["geometry_types"]


def test_feature_collection_summary_ignores_invalid_geom():
    features = [
        {"geometry": {"type": "Point", "coordinates": [-66.0, 18.0]}},
        {"geometry": None},
        {"geometry": {"type": "Point"}},  # missing coords
    ]
    s = feature_collection_summary(features)
    assert s["feature_count"] == 1  # only the valid one counted


# ──────────────────────────────────────────────────────────────────────────
# T5-41: standardized GeoJSON Feature _meta block
# ──────────────────────────────────────────────────────────────────────────

def test_geojson_feature_meta_has_three_required_keys():
    from provenance_utils import geojson_feature_meta
    block = geojson_feature_meta(
        producer_module="integration.pr_intel_adapter",
        source_artifact="gis_airspace_features.geojson",
    )
    assert set(block.keys()) == {"producer_module", "source_artifact", "produced_at"}
    assert block["producer_module"] == "integration.pr_intel_adapter"
    assert block["source_artifact"] == "gis_airspace_features.geojson"


def test_geojson_feature_meta_default_timestamp_is_iso_utc():
    from provenance_utils import geojson_feature_meta
    block = geojson_feature_meta(producer_module="m", source_artifact="a")
    # ISO 8601 with Z suffix: YYYY-MM-DDTHH:MM:SSZ
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", block["produced_at"])


def test_geojson_feature_meta_explicit_timestamp_respected():
    from provenance_utils import geojson_feature_meta
    block = geojson_feature_meta(
        producer_module="m", source_artifact="a",
        produced_at="2024-01-01T00:00:00Z",
    )
    assert block["produced_at"] == "2024-01-01T00:00:00Z"


def test_geojson_feature_meta_shared_across_features_in_same_run():
    """Multiple Features from the same producer can share one block reference —
    they should compare equal so downstream consumers can cluster by run."""
    from provenance_utils import geojson_feature_meta
    block_a = geojson_feature_meta(
        producer_module="m", source_artifact="a",
        produced_at="2024-01-01T00:00:00Z",
    )
    block_b = geojson_feature_meta(
        producer_module="m", source_artifact="a",
        produced_at="2024-01-01T00:00:00Z",
    )
    assert block_a == block_b
