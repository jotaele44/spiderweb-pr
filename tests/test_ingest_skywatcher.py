"""Gate: Spiderweb accepts a valid synthetic Skywatcher bridge fixture and
rejects invalid / incompatible ones. Synthetic data only; temp DB cleaned up
by pytest's tmp_path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integration import skywatcher_bridge as bridge  # noqa: E402


def _valid_record():
    return {
        "schema_version": "1.0",
        "export_id": "pkg_" + "a" * 32,
        "generated_at_utc": "2026-01-01T01:00:00Z",
        "source_snapshot_id": "snap1",
        "flight_id": "FL_TEST",
        "aircraft_id": "N123",
        "validated_time_interval": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:20:00Z"},
        "validated_track_geometry": {"type": "LineString", "coordinates": [[-66.0, 18.1], [-66.1, 18.2]]},
        "mission_classification": {"value": "patrol", "status": "highly_speculative", "evidence_score": 0.4, "threshold": 0.85},
        "anomaly_flags": [],
        "confidence": {"score": 0.72, "method": "skywatcher_fr24_fusion"},
        "review_status": "approved",
        "coordinate_method": "per_screenshot_affine",
        "provenance": {"source_id": "snap1", "lineage": [{"step": "skywatcher_fr24_export"}]},
    }


def _write_package(dir_path: Path, records):
    dir_path.mkdir(parents=True, exist_ok=True)
    with (dir_path / "bridge_records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    (dir_path / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "export_id": "pkg_" + "a" * 32,
        "producer": "skywatcher-pr", "mode": "test",
        "record_counts": {"flights": len(records)},
    }))


def test_accepts_valid_fixture(tmp_path):
    pkg = tmp_path / "pkg"
    _write_package(pkg, [_valid_record()])
    dbp = str(tmp_path / "sw.db")
    summary = bridge.ingest_package(pkg, dbp)
    assert summary["ingested"] == 1
    assert summary["rejected"] == 0
    import sqlite3
    conn = sqlite3.connect(dbp)
    try:
        assert conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM track_points").fetchone()[0] == 2
    finally:
        conn.close()


def test_rejects_invalid_fixture(tmp_path):
    pkg = tmp_path / "pkg"
    bad = {"schema_version": "1.0", "flight_id": "X"}  # missing required fields
    _write_package(pkg, [bad])
    summary = bridge.ingest_package(pkg, str(tmp_path / "sw.db"))
    assert summary["ingested"] == 0
    assert summary["rejected"] == 1


def test_rejects_prohibited_confirmed_label(tmp_path):
    pkg = tmp_path / "pkg"
    rec = _valid_record()
    rec["mission_classification"]["value"] = "confirmed"  # terminal-accept token
    _write_package(pkg, [rec])
    summary = bridge.ingest_package(pkg, str(tmp_path / "sw.db"))
    assert summary["ingested"] == 0
    assert summary["rejected"] == 1
    assert any("prohibited" in e for e in summary["rejects"][0]["errors"])


def test_missing_package_raises(tmp_path):
    import pytest
    with pytest.raises(bridge.BridgeValidationError):
        bridge.ingest_package(tmp_path / "does_not_exist", str(tmp_path / "sw.db"))


def test_missing_manifest_raises(tmp_path):
    import pytest
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "bridge_records.jsonl").write_text(json.dumps(_valid_record()) + "\n")
    with pytest.raises(bridge.BridgeValidationError):
        bridge.ingest_package(pkg, str(tmp_path / "sw.db"))


def test_rejects_bad_datetime(tmp_path):
    pkg = tmp_path / "pkg"
    rec = _valid_record()
    rec["validated_time_interval"] = {"start": "not-a-date", "end": None}
    _write_package(pkg, [rec])
    summary = bridge.ingest_package(pkg, str(tmp_path / "sw.db"))
    assert summary["ingested"] == 0
    assert summary["rejected"] == 1
    assert any("datetime" in e for e in summary["rejects"][0]["errors"])
