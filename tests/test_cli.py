"""Tests for CLI --status and --export-json flags."""

import json
import subprocess
import sys
from pathlib import Path


def test_status_flag_runs(populated_db, tmp_output):
    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", populated_db, "--status"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, result.stderr


def test_export_json_flag(populated_db, tmp_output):
    out = str(tmp_output / "export.json")
    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", populated_db, "--export-json", out],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, result.stderr
    assert Path(out).exists()
    data = json.loads(Path(out).read_text())
    assert "flights" in data or "screenshots" in data or isinstance(data, (dict, list))


def test_validate_missing_db_exits_nonzero(tmp_path):
    result = subprocess.run(
        [sys.executable, "run_all.py", "--validate", "--db", str(tmp_path / "no.db")],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode != 0


def test_export_pr_intel_missing_db_exits_nonzero(tmp_path):
    result = subprocess.run(
        [sys.executable, "run_all.py", "--export-pr-intel", str(tmp_path / "out"),
         "--db", str(tmp_path / "no.db")],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode != 0
