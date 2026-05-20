"""Tests for CalibrationDriver in calibrate_scoring.py."""

import json
from pathlib import Path

import pytest

from calibrate_scoring import (
    REQUIRED_REPORT_KEYS,
    CalibrationDriver,
    MIN_OPERATIONAL_CANDIDATES,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_geojson(path: Path, features: list) -> None:
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


def _write_gap_audit(path: Path, duplicates_removed: int = 0) -> None:
    path.write_text(
        json.dumps({"gaps": {"dedup_gap": {"duplicates_removed": duplicates_removed}}}),
        encoding="utf-8",
    )


def _feature(tier="T4", mbil="MBIL-2", hydro="no", utility="yes", terrain="urban"):
    return {
        "type": "Feature",
        "geometry": None,
        "properties": {
            "evidence_tier": tier,
            "mbil_class": mbil,
            "hydro_overlap": hydro,
            "utility_overlap": utility,
            "terrain_context": terrain,
        },
    }


# ── CalibrationDriver ─────────────────────────────────────────────────────────

def test_empty_dir_has_all_required_report_keys(tmp_path):
    report = CalibrationDriver(str(tmp_path)).run()
    for key in REQUIRED_REPORT_KEYS:
        assert key in report, f"Missing key: {key}"


def test_empty_dir_status_is_pass(tmp_path):
    report = CalibrationDriver(str(tmp_path)).run()
    assert report["status"] == "PASS"


def test_empty_dir_candidate_count_zero(tmp_path):
    report = CalibrationDriver(str(tmp_path)).run()
    assert report["candidate_count"] == 0


def test_empty_dir_reports_both_missing_inputs(tmp_path):
    report = CalibrationDriver(str(tmp_path)).run()
    assert len(report["missing_inputs"]) == 2


def test_report_written_to_disk(tmp_path):
    CalibrationDriver(str(tmp_path)).run()
    assert (tmp_path / "calibration_report.json").exists()


def test_report_json_is_valid(tmp_path):
    CalibrationDriver(str(tmp_path)).run()
    data = json.loads((tmp_path / "calibration_report.json").read_text())
    assert isinstance(data, dict)


def test_fixture_mode_for_small_sample(tmp_path):
    _write_geojson(tmp_path / "spiderweb_overlay_candidates.geojson", [_feature()])
    _write_gap_audit(tmp_path / "spiderweb_gap_audit.json")
    report = CalibrationDriver(str(tmp_path)).run()
    assert report["baseline_mode"] == "fixture"
    assert report["candidate_count"] == 1


def test_tier_distribution_counted_correctly(tmp_path):
    features = [_feature(tier="T4")] * 3 + [_feature(tier="T1")] * 1
    _write_geojson(tmp_path / "spiderweb_overlay_candidates.geojson", features)
    _write_gap_audit(tmp_path / "spiderweb_gap_audit.json")
    report = CalibrationDriver(str(tmp_path)).run()
    assert report["tier_distribution"].get("T4") == 3
    assert report["tier_distribution"].get("T1") == 1


def test_dedup_rate_calculation(tmp_path):
    features = [_feature()] * 10
    _write_geojson(tmp_path / "spiderweb_overlay_candidates.geojson", features)
    _write_gap_audit(tmp_path / "spiderweb_gap_audit.json", duplicates_removed=2)
    report = CalibrationDriver(str(tmp_path)).run()
    # 10 remaining + 2 removed = 12 total → 2/12
    assert report["dedup_rate"] == round(2 / 12, 4)


def test_zero_candidates_dedup_rate_is_zero(tmp_path):
    report = CalibrationDriver(str(tmp_path)).run()
    assert report["dedup_rate"] == 0.0


def test_calibration_flags_sorted_by_metric(tmp_path):
    features = [_feature(hydro="no", utility="no")] * 5
    _write_geojson(tmp_path / "spiderweb_overlay_candidates.geojson", features)
    _write_gap_audit(tmp_path / "spiderweb_gap_audit.json")
    report = CalibrationDriver(str(tmp_path)).run()
    flags = report["calibration_flags"]
    metrics = [f["metric"] for f in flags]
    assert metrics == sorted(metrics)


def test_custom_output_dir(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    out_dir = tmp_path / "out"
    CalibrationDriver(str(export_dir), output_dir=str(out_dir)).run()
    assert (out_dir / "calibration_report.json").exists()
