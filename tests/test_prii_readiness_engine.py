"""Tests for PRIIReadinessEngine: contract, verdict, blocker/warning routing."""

import json
from pathlib import Path

import pytest

from prii_readiness_engine import (
    READINESS_STATUS_DEGRADED,
    READINESS_STATUS_NOT_READY,
    READINESS_STATUS_READY,
    REQUIRED_REPORT_KEYS,
    PRIIReadinessEngine,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _passing_integration_report() -> dict:
    return {
        "generated_at": "2024-03-15T08:00:00Z",
        "overall_status": "PASS",
        "gates": {
            "schema_validation":      {"status": "PASS", "records_validated": 9, "invalid": 0},
            "coordinate_coverage":    {"status": "PASS", "pct_with_coords": 1.0, "threshold": 0.70},
            "ocr_confidence_gate":    {"status": "PASS", "avg_confidence": 0.85, "threshold": 0.50},
            "evidence_chain_coverage":{"status": "PASS", "pct_with_screenshot": 1.0, "threshold": 0.50},
            "export_completeness":    {"status": "PASS", "files_generated": 9, "missing": []},
            "temporal_integrity":     {"status": "PASS", "violations": 0},
        },
    }


def _passing_calibration_report(export_dir: Path) -> dict:
    return {
        "generated_at": "2024-03-15T08:00:00Z",
        "export_dir": str(export_dir),
        "baseline_mode": "operational",
        "status": "PASS",
        "missing_inputs": [],
        "candidate_count": 100,
        "tier_distribution": {"T4": 70, "T3": 20, "T2": 7, "T1": 3},
        "calibration_flags": [],
    }


def _write(export_dir: Path, filename: str, data: dict) -> None:
    (export_dir / filename).write_text(json.dumps(data), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_ready_with_both_inputs_passing(tmp_path):
    _write(tmp_path, "integration_report.json", _passing_integration_report())
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))
    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_READY
    assert report["blockers"] == []
    assert report["warnings"] == []


def test_not_ready_when_prii_gate_fails(tmp_path):
    integration = _passing_integration_report()
    integration["overall_status"] = "FAIL"
    integration["gates"]["coordinate_coverage"]["status"] = "FAIL"
    integration["gates"]["coordinate_coverage"]["pct_with_coords"] = 0.45
    _write(tmp_path, "integration_report.json", integration)
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))

    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_NOT_READY
    assert len(report["blockers"]) >= 1
    blocker_sources = [b["source"] for b in report["blockers"]]
    assert "prii_gate" in blocker_sources
    gate_names = [b["gate"] for b in report["blockers"] if b["source"] == "prii_gate"]
    assert "coordinate_coverage" in gate_names


def test_not_ready_when_calibration_fails(tmp_path):
    _write(tmp_path, "integration_report.json", _passing_integration_report())
    cal = _passing_calibration_report(tmp_path)
    cal["status"] = "FAIL"
    cal["baseline_mode"] = "operational"
    cal["calibration_flags"] = [
        {"metric": "pct_T4", "value": 0.85, "expected_max": 0.70,
         "action": "investigate tier thresholds"},
    ]
    _write(tmp_path, "calibration_report.json", cal)

    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_NOT_READY
    cal_blockers = [b for b in report["blockers"] if b["source"] == "calibration"]
    assert len(cal_blockers) == 1
    assert cal_blockers[0]["flag"] == "pct_T4"


def test_degraded_when_calibration_warns(tmp_path):
    _write(tmp_path, "integration_report.json", _passing_integration_report())
    cal = _passing_calibration_report(tmp_path)
    cal["status"] = "WARN"
    cal["baseline_mode"] = "fixture"
    cal["candidate_count"] = 6
    cal["calibration_flags"] = [
        {"metric": "pct_hydro_yes", "value": 0.02, "expected_min": 0.05,
         "action": "expand HYDRO_LOCATIONS"},
    ]
    _write(tmp_path, "calibration_report.json", cal)

    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_DEGRADED
    assert report["blockers"] == []
    cal_warnings = [w for w in report["warnings"] if w["source"] == "calibration"]
    assert len(cal_warnings) == 1
    assert "WARN" in cal_warnings[0]["detail"]


def test_degraded_when_integration_report_missing(tmp_path):
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))
    # No integration_report.json

    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_DEGRADED
    assert report["blockers"] == []
    prii_warnings = [w for w in report["warnings"] if w["source"] == "prii_report"]
    assert len(prii_warnings) == 1
    assert "integration_report.json" in report["missing_inputs"]


def test_degraded_when_prii_reports_no_data(tmp_path):
    # An empty-DB export reports NO_DATA — no hard failure, but it must not
    # resolve to READY.
    integration = _passing_integration_report()
    integration["overall_status"] = "NO_DATA"
    for gate in integration["gates"].values():
        if gate["status"] == "PASS":
            gate["status"] = "NO_DATA"
    integration["gates"]["export_completeness"]["status"] = "PASS"
    _write(tmp_path, "integration_report.json", integration)
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))

    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_DEGRADED
    assert report["blockers"] == []
    prii_warnings = [w for w in report["warnings"] if w["source"] == "prii_report"]
    assert len(prii_warnings) == 1
    assert "NO_DATA" in prii_warnings[0]["detail"]


def test_report_written_to_disk(tmp_path):
    _write(tmp_path, "integration_report.json", _passing_integration_report())
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))
    PRIIReadinessEngine(str(tmp_path)).assess()
    report_path = tmp_path / "prii_readiness_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["readiness_status"] == READINESS_STATUS_READY


def test_report_has_required_keys(tmp_path):
    _write(tmp_path, "integration_report.json", _passing_integration_report())
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))
    report = PRIIReadinessEngine(str(tmp_path)).assess()
    for key in REQUIRED_REPORT_KEYS:
        assert key in report, f"Required key missing from readiness report: {key}"


def test_missing_both_inputs_does_not_crash(tmp_path):
    # Empty export dir — engine should produce DEGRADED, not raise
    report = PRIIReadinessEngine(str(tmp_path)).assess()
    assert report["readiness_status"] == READINESS_STATUS_DEGRADED
    assert isinstance(report["blockers"], list)
    assert isinstance(report["warnings"], list)
    assert len(report["missing_inputs"]) == 2
