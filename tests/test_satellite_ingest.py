"""Tests for satellite_ingest.py (tasks 41-50)."""

import hashlib
import json
from pathlib import Path

import pytest

from readiness.satellite_ingest import SatelliteIngest, PR_LAT_MAX, PR_LAT_MIN, PR_LON_MAX, PR_LON_MIN


# ── helpers ───────────────────────────────────────────────────────────────────

def _valid_manifest(synthetic=True):
    checksum = "a" * 64
    return {
        "manifest_id": "SAT-TEST-001",
        "schema_version": "1.0",
        "producer": "test-suite",
        "created_at": "2024-03-15T10:00:00Z",
        "synthetic": synthetic,
        "source": {
            "provider": "ESA",
            "collection": "sentinel-2-l2a",
            "platform": "Sentinel-2A",
            "instrument": "MSI",
        },
        "acquisition": {
            "acquired_at": "2024-03-14T14:00:00Z",
            "processed_at": "2024-03-15T02:00:00Z",
            "license": "Copernicus Open Access",
        },
        "asset": {
            "source_uri": "s3://fixture-bucket/pr/img.tif",
            "checksum_sha256": checksum,
            "media_type": "image/tiff",
        },
        "geometry": {
            "crs": "EPSG:4326",
            "footprint": {
                "type": "Polygon",
                "coordinates": [[
                    [-67.0, 18.0], [-66.0, 18.0],
                    [-66.0, 18.5], [-67.0, 18.5], [-67.0, 18.0],
                ]],
            },
            "bbox": [-67.0, 18.0, -66.0, 18.5],
        },
        "puerto_rico": {"region": "mainland"},
        "quality": {
            "cloud_cover_pct": 12.5,
            "geometric_confidence": 0.92,
            "source_reliability": "high",
        },
        "lineage": {"processing_pipeline": "spiderweb-sat-ingest-v1"},
    }


def _write_manifest(tmp_path, data, name="manifest.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ── ingest: accepted / rejected ───────────────────────────────────────────────

def test_valid_manifest_accepted(tmp_path):
    path = _write_manifest(tmp_path, _valid_manifest())
    result = SatelliteIngest(output_dir=str(tmp_path / "out"), dry_run=True).ingest(path)
    assert result["status"] == "accepted"
    assert result["errors"] == []


def test_missing_required_field_rejected(tmp_path):
    m = _valid_manifest()
    del m["manifest_id"]
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(output_dir=str(tmp_path / "out"), dry_run=True).ingest(path)
    assert result["status"] == "rejected"
    assert len(result["errors"]) >= 1


def test_missing_file_rejected(tmp_path):
    result = SatelliteIngest(dry_run=True).ingest(str(tmp_path / "nonexistent.json"))
    assert result["status"] == "rejected"
    assert any("not found" in e for e in result["errors"])


def test_malformed_json_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    result = SatelliteIngest(dry_run=True).ingest(str(p))
    assert result["status"] == "rejected"


# ── fixture-mode rule ─────────────────────────────────────────────────────────

def test_synthetic_false_with_fixture_uri_rejected(tmp_path):
    m = _valid_manifest(synthetic=False)
    m["asset"]["source_uri"] = "s3://fixture-bucket/pr/img.tif"
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "rejected"
    assert any("fixture" in e.lower() for e in result["errors"])


def test_synthetic_false_with_real_uri_accepted(tmp_path):
    m = _valid_manifest(synthetic=False)
    m["asset"]["source_uri"] = "s3://real-bucket/pr/sentinel2/2024-03-14.tif"
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "accepted"


def test_synthetic_true_allows_fixture_uri(tmp_path):
    m = _valid_manifest(synthetic=True)
    m["asset"]["source_uri"] = "s3://test-data/mock-img.tif"
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "accepted"


# ── bbox overlap ──────────────────────────────────────────────────────────────

def test_bbox_outside_pr_rejected(tmp_path):
    m = _valid_manifest()
    m["geometry"]["bbox"] = [-74.3, 40.4, -73.7, 40.9]  # NYC
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "rejected"
    assert any("overlap" in e.lower() or "bbox" in e.lower() for e in result["errors"])


def test_bbox_at_pr_boundary_accepted(tmp_path):
    m = _valid_manifest()
    m["geometry"]["bbox"] = [PR_LON_MIN, PR_LAT_MIN, PR_LON_MAX, PR_LAT_MAX]
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "accepted"


# ── checksum verification ─────────────────────────────────────────────────────

def test_checksum_mismatch_rejected(tmp_path):
    asset_file = tmp_path / "img.tif"
    asset_file.write_bytes(b"real data")
    correct_hash = hashlib.sha256(b"real data").hexdigest()

    m = _valid_manifest()
    m["asset"]["local_path"] = str(asset_file)
    m["asset"]["checksum_sha256"] = "b" * 64  # wrong hash
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "rejected"
    assert any("checksum" in e.lower() for e in result["errors"])


def test_checksum_match_accepted(tmp_path):
    asset_file = tmp_path / "img.tif"
    asset_file.write_bytes(b"real data")
    correct_hash = hashlib.sha256(b"real data").hexdigest()

    m = _valid_manifest()
    m["asset"]["local_path"] = str(asset_file)
    m["asset"]["checksum_sha256"] = correct_hash
    del m["asset"]["source_uri"]  # use local_path only
    path = _write_manifest(tmp_path, m)
    result = SatelliteIngest(dry_run=True).ingest(path)
    assert result["status"] == "accepted"


# ── dry-run vs write ──────────────────────────────────────────────────────────

def test_dry_run_does_not_write(tmp_path):
    path = _write_manifest(tmp_path, _valid_manifest())
    out_dir = tmp_path / "out"
    SatelliteIngest(output_dir=str(out_dir), dry_run=True).ingest(path)
    assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0


def test_non_dry_run_writes_manifest(tmp_path):
    path = _write_manifest(tmp_path, _valid_manifest())
    out_dir = tmp_path / "out"
    result = SatelliteIngest(output_dir=str(out_dir), dry_run=False).ingest(path)
    assert result["status"] == "accepted"
    assert result["output_path"] is not None
    assert Path(result["output_path"]).exists()


# ── Phase 9: Production Hardening ────────────────────────────────────────────

def test_ingest_batch_returns_list(tmp_path):
    paths = [_write_manifest(tmp_path, _valid_manifest(), name=f"m{i}.json") for i in range(3)]
    ingester = SatelliteIngest(dry_run=True)
    results = ingester.ingest_batch(paths)
    assert isinstance(results, list)
    assert len(results) == 3


def test_ingest_batch_all_accepted(tmp_path):
    paths = [_write_manifest(tmp_path, _valid_manifest(), name=f"m{i}.json") for i in range(2)]
    ingester = SatelliteIngest(dry_run=True)
    results = ingester.ingest_batch(paths)
    assert all(r["status"] == "accepted" for r in results)


def test_get_ingest_summary_counts(tmp_path):
    paths = [_write_manifest(tmp_path, _valid_manifest(), name=f"m{i}.json") for i in range(4)]
    ingester = SatelliteIngest(dry_run=True)
    results = ingester.ingest_batch(paths)
    summary = SatelliteIngest.get_ingest_summary(results)
    assert summary["total"] == 4
    assert summary["accepted"] == 4
    assert summary["rejected"] == 0
    assert summary["acceptance_rate"] == 1.0


def test_get_ingest_summary_empty():
    summary = SatelliteIngest.get_ingest_summary([])
    assert summary["total"] == 0
    assert summary["acceptance_rate"] == 0.0
