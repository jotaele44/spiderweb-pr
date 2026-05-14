"""CLI tests for --assess-readiness flag."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _write(path: Path, filename: str, data: dict) -> None:
    (path / filename).write_text(json.dumps(data), encoding="utf-8")


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
        "calibration_flags": [],
    }


def _run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "run_all.py"] + args,
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def test_assess_readiness_cli_exits_nonzero_if_dir_missing(tmp_path):
    result = _run(["--assess-readiness", str(tmp_path / "nonexistent")])
    assert result.returncode != 0
    assert "Error: directory not found" in result.stdout


def test_assess_readiness_cli_exits_zero_when_ready(tmp_path):
    _write(tmp_path, "integration_report.json", _passing_integration_report())
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))
    result = _run(["--assess-readiness", str(tmp_path)])
    assert result.returncode == 0, result.stdout
    assert "READY" in result.stdout


def test_assess_readiness_cli_exits_nonzero_when_not_ready(tmp_path):
    integration = _passing_integration_report()
    integration["overall_status"] = "FAIL"
    integration["gates"]["coordinate_coverage"]["status"] = "FAIL"
    integration["gates"]["coordinate_coverage"]["pct_with_coords"] = 0.40
    _write(tmp_path, "integration_report.json", integration)
    _write(tmp_path, "calibration_report.json", _passing_calibration_report(tmp_path))
    result = _run(["--assess-readiness", str(tmp_path)])
    assert result.returncode != 0
    assert "NOT_READY" in result.stdout


def test_assess_readiness_cli_exits_zero_when_degraded(tmp_path):
    # Dir present but no report files → DEGRADED (warnings, not blocking)
    result = _run(["--assess-readiness", str(tmp_path)])
    assert result.returncode == 0, result.stdout
    assert "DEGRADED" in result.stdout
