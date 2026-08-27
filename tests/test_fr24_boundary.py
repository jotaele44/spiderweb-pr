"""Regression gates for the Spiderweb/Skywatcher ownership boundary."""

from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
from contextlib import closing
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
DOWNSTREAM_SCHEMA = REPO_ROOT / "tests" / "fixtures" / "downstream_phase_ready.sql"

REMOVED_PATHS = (
    "pipeline/flight_analyzer.py",
    "pipeline/hardened_pipeline.py",
    "scripts/ocr_checkpoint.py",
    "scripts/ocr_full.py",
    "scripts/ocr_parallel.py",
    "integration/skywatcher_bridge.py",
    "schemas/spiderweb_bridge.schema.json",
    "tests/test_ingest_skywatcher.py",
)


@pytest.mark.parametrize("relative_path", REMOVED_PATHS)
def test_removed_fr24_paths_stay_absent(relative_path: str) -> None:
    assert not (REPO_ROOT / relative_path).exists()


@pytest.mark.parametrize(
    "module_name",
    ("pipeline.flight_analyzer", "pipeline.hardened_pipeline"),
)
def test_removed_fr24_modules_are_not_importable(module_name: str) -> None:
    assert importlib.util.find_spec(module_name) is None


@pytest.mark.parametrize("removed_args", (("--phase", "1"), ("--images", "1")))
def test_cli_rejects_removed_fr24_arguments(removed_args: tuple[str, ...]) -> None:
    result = subprocess.run(
        [sys.executable, "run_all.py", *removed_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_downstream_run_does_not_create_a_missing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"
    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", str(db_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "downstream database not found" in result.stderr
    assert not db_path.exists()


def test_downstream_run_rejects_incomplete_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "incomplete.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("CREATE TABLE flights (flight_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE track_points (id INTEGER PRIMARY KEY)")
        conn.commit()

    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", str(db_path), "--status"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "downstream database is not phase-ready; missing columns:" in result.stderr
    assert "flights(" in result.stderr
    assert "track_points(" in result.stderr


def test_downstream_run_rejects_unreadable_database(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"not a sqlite database")

    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", str(db_path), "--status"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "downstream database is unreadable:" in result.stderr


def test_downstream_run_accepts_uri_sensitive_database_path(tmp_path: Path) -> None:
    db_path = tmp_path / "phase ready ?# database.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(DOWNSTREAM_SCHEMA.read_text(encoding="utf-8"))
        conn.commit()

    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", str(db_path), "--status"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "db_args",
    (
        ("--status",),
        ("--report", "daily"),
        ("--aircraft", "N123PR"),
        ("--validate",),
        ("--export-pr-intel", "{out}"),
        ("--export-spiderweb", "{out}"),
        ("--release-check",),
    ),
)
def test_db_commands_do_not_create_a_missing_database(
    tmp_path: Path, db_args: tuple[str, ...]
) -> None:
    db_path = tmp_path / "missing database.db"
    output_path = tmp_path / "out"
    resolved_args = tuple(
        str(output_path) if value == "{out}" else value for value in db_args
    )
    result = subprocess.run(
        [sys.executable, "run_all.py", "--db", str(db_path), *resolved_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "downstream database not found" in result.stderr
    assert not db_path.exists()
    assert not output_path.exists()


def test_backend_rejects_removed_pipeline_inputs() -> None:
    from server.backend.main import PipelineRunRequest

    with pytest.raises(ValidationError):
        PipelineRunRequest.model_validate({"phase": 1})
    with pytest.raises(ValidationError):
        PipelineRunRequest.model_validate({"images": 1})


def test_retained_geo_anchor_module_remains_available() -> None:
    assert importlib.util.find_spec("pipeline.geo_anchors") is not None
    module = import_module("pipeline.geo_anchors")
    assert not hasattr(module, "match_ocr_anchors")


def test_no_premature_skywatcher_consumer_flag() -> None:
    source = (REPO_ROOT / "run_all.py").read_text(encoding="utf-8")
    assert "--ingest-skywatcher" not in source
