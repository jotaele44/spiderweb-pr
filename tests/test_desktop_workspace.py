"""Workspace-binding regressions for the Spiderweb desktop adapter."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from desktop import setup_actions

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_prepare_workspace_seeds_the_selected_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SPIDERWEB_DATA_HOME", str(tmp_path))

    setup_actions.prepare_workspace()

    database = tmp_path / "server" / "priis.db"
    assert (tmp_path / "exports").is_dir()
    assert database.is_file()
    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"agencies", "vendors", "sites", "contracts", "events"} <= tables
    assert not list(database.parent.glob(f".{database.name}.seed-*"))


def test_prepare_workspace_preserves_an_existing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SPIDERWEB_DATA_HOME", str(tmp_path))
    database = tmp_path / "server" / "priis.db"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"user-owned-database")

    setup_actions.prepare_workspace()

    assert database.read_bytes() == b"user-owned-database"


def test_prepare_workspace_does_not_publish_a_partial_database(tmp_path, monkeypatch):
    from server.ingestion import seed_demo

    monkeypatch.setenv("SPIDERWEB_DATA_HOME", str(tmp_path))

    def fail_after_writing(database: Path) -> None:
        database.write_bytes(b"partial-database")
        raise RuntimeError("simulated seed failure")

    monkeypatch.setattr(seed_demo, "main", fail_after_writing)

    setup_actions.prepare_workspace()

    server_dir = tmp_path / "server"
    assert not (server_dir / "priis.db").exists()
    assert list(server_dir.iterdir()) == []


def test_app_server_binds_backend_to_selected_data_home(tmp_path):
    env = os.environ.copy()
    env["SPIDERWEB_DATA_HOME"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import desktop.app_server as adapter; "
                "from server.backend import main as backend; "
                "print(adapter.OUTPUTS_DIR); print(backend.DB_PATH)"
            ),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        str(tmp_path / "exports"),
        str(tmp_path / "server" / "priis.db"),
    ]
