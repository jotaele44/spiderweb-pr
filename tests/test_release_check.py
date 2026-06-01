"""Tests for the release_check.ReleaseCheck umbrella gate.

Covers the structural invariants the release gate must hold regardless of
input state: it never crashes on empty/missing DB, produces a complete JSON
report with all sections, is idempotent, and respects mode (normal/demo/strict).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from release_check import (  # noqa: E402
    GATING_STAGES,
    PASS,
    SKIPPED,
    WARNING,
    ReleaseCheck,
)


# ── basics ──────────────────────────────────────────────────────────────────


def test_run_with_missing_db_normal_mode_does_not_crash(tmp_path):
    """The defining release-gate invariant: gate runs cleanly on a missing DB
    in normal mode, writes a complete JSON report with all sections."""
    out_dir = tmp_path / "release_out"
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(out_dir), mode="normal", run_tests=False)
    report = rc.run()

    # All sections present
    for section in ("metadata", "syntax_check", "core_tests",
                    "validate", "export_pr_intel", "export_spiderweb",
                    "earthgpt_selftest", "overall_status", "failure_reasons"):
        assert section in report, f"missing section: {section}"

    # File written
    report_path = out_dir / "release_report.json"
    assert report_path.exists()
    on_disk = json.loads(report_path.read_text())
    assert on_disk["overall_status"] == report["overall_status"]


def test_metadata_has_eight_reproducibility_keys(tmp_path):
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="normal", run_tests=False)
    report = rc.run()
    md = report["metadata"]
    for key in ("timestamp_utc", "repo_commit", "python_version", "platform",
                "command", "input_paths", "input_sha256s", "mode"):
        assert key in md, f"reproducibility key missing: {key}"


def test_missing_db_skips_validate_and_export_stages(tmp_path):
    """Stages that need the DB return SKIPPED softly in normal mode."""
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="normal", run_tests=False)
    report = rc.run()
    assert report["validate"]["status"] == SKIPPED
    assert report["export_pr_intel"]["status"] == SKIPPED
    assert report["export_spiderweb"]["status"] == SKIPPED


def test_syntax_check_runs_on_source_tree(tmp_path):
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="normal", run_tests=False)
    report = rc.run()
    sc = report["syntax_check"]
    assert sc["status"] == PASS  # we expect the live tree to compile
    assert sc["files_checked"] > 0


def test_earthgpt_selftest_is_non_gating(tmp_path):
    """EarthGPT degradation must never appear in overall_status FAIL."""
    assert "earthgpt_selftest" not in GATING_STAGES
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="normal", run_tests=False)
    report = rc.run()
    # If earthgpt is FAIL/WARNING, overall must not include it in failure_reasons
    assert not any("earthgpt" in fr for fr in report.get("failure_reasons", []))


# ── modes ───────────────────────────────────────────────────────────────────


def test_demo_mode_stamps_manifest(tmp_path):
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="demo", run_tests=False)
    report = rc.run()
    assert report["metadata"]["mode"] == "demo"
    assert report.get("mode") == "demo"
    assert "demo_warning" in report


def test_strict_mode_on_missing_db_exits_2(tmp_path):
    """Strict mode is the hard gate — missing DB → structured SystemExit(2)."""
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="strict", run_tests=False)
    with pytest.raises(SystemExit) as ei:
        rc.run()
    assert ei.value.code == 2


# ── idempotency ─────────────────────────────────────────────────────────────


def test_run_is_idempotent(tmp_path):
    """Running twice on the same inputs produces two valid reports without crash."""
    out_dir = tmp_path / "out"
    rc1 = ReleaseCheck(str(tmp_path / "nope.db"), str(out_dir),
                       mode="normal", run_tests=False)
    r1 = rc1.run()
    rc2 = ReleaseCheck(str(tmp_path / "nope.db"), str(out_dir),
                       mode="normal", run_tests=False)
    r2 = rc2.run()
    # Both produced a report file at the same path; structure identical
    assert r1["overall_status"] == r2["overall_status"]
    assert set(r1.keys()) == set(r2.keys())
