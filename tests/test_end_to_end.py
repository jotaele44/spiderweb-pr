"""End-to-end CLI tests: --validate --export-pr-intel --export-spiderweb."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


CLI = str(Path(__file__).parent.parent / "run_all.py")


def run(args, cwd=None):
    return subprocess.run(
        [sys.executable, CLI] + args,
        capture_output=True, text=True,
        cwd=cwd or str(Path(__file__).parent.parent),
    )


def test_validate_flag(populated_db):
    result = run(["--db", populated_db, "--validate"])
    assert result.returncode == 0, result.stderr


def test_export_pr_intel_flag(populated_db, tmp_output):
    out = str(tmp_output / "pr_intel")
    result = run(["--db", populated_db, "--export-pr-intel", out])
    assert result.returncode == 0, result.stderr
    assert (Path(out) / "integration_report.json").exists()


def test_export_spiderweb_flag(populated_db, tmp_output):
    out = str(tmp_output / "spiderweb")
    result = run(["--db", populated_db, "--export-spiderweb", out])
    assert result.returncode == 0, result.stderr
    assert (Path(out) / "spiderweb_ingest_manifest.json").exists()


def test_combined_export_flags(populated_db, tmp_output):
    pr_out = str(tmp_output / "pr_intel")
    sw_out = str(tmp_output / "spiderweb")
    result = run([
        "--db", populated_db,
        "--validate",
        "--export-pr-intel", pr_out,
        "--export-spiderweb", sw_out,
    ])
    assert result.returncode == 0, result.stderr

    report = json.loads((Path(pr_out) / "integration_report.json").read_text())
    assert "overall_status" in report
    assert "gates" in report


def test_integration_report_all_gates_present(populated_db, tmp_output):
    out = str(tmp_output / "pr_intel")
    run(["--db", populated_db, "--export-pr-intel", out])
    report = json.loads((Path(out) / "integration_report.json").read_text())
    expected_gates = {
        "schema_validation", "coordinate_coverage", "ocr_confidence_gate",
        "evidence_chain_coverage", "export_completeness", "temporal_integrity",
    }
    assert set(report["gates"].keys()) == expected_gates


def test_export_does_not_break_status(populated_db, tmp_output):
    out = str(tmp_output / "pr")
    r1 = run(["--db", populated_db, "--export-pr-intel", out])
    r2 = run(["--db", populated_db, "--status"])
    assert r1.returncode == 0
    assert r2.returncode == 0
