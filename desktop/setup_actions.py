"""Idempotent Spiderweb workspace preparation for the native setup UI."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _rows(connection: sqlite3.Connection, table: str, order: str = "") -> list[dict]:
    try:
        statement = f"SELECT * FROM {table} {order} LIMIT 5000"
        return [dict(row) for row in connection.execute(statement)]
    except sqlite3.Error:
        return []


def _export_database(database: Path, output: Path) -> None:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        profiles = _rows(connection, "aircraft_profiles")
        payload = {
            "exported_at": datetime.now(UTC).isoformat(),
            "db_path": str(database),
            "flights": _rows(connection, "flights", "ORDER BY takeoff_time DESC"),
            "aircraft_profiles": profiles,
            "alerts": _rows(connection, "alerts", "ORDER BY triggered_at DESC"),
            "anomalies": _rows(
                connection, "gis_anomalies", "ORDER BY detected_at DESC"
            ),
        }
    finally:
        connection.close()
    output.write_text(json.dumps(payload, default=str) + "\n", encoding="utf-8")


def prepare_workspace() -> None:
    workspace = Path(os.environ["SPIDERWEB_DATA_HOME"])
    output = workspace / "exports" / "dashboard_data.json"
    if output.exists():
        return
    output.parent.mkdir(parents=True, exist_ok=True)

    bundled = REPO_ROOT / "outputs" / "dashboard_data.json"
    if bundled.is_file():
        shutil.copy2(bundled, output)
        return

    candidates = [
        workspace / "data" / "flight_database.db",
        Path.home() / "flight_database.db",
    ]
    database = next((path for path in candidates if path.is_file()), None)
    if database is not None:
        _export_database(database, output)
        return

    output.write_text(
        json.dumps(
            {
                "exported_at": datetime.now(UTC).isoformat(),
                "db_path": None,
                "flights": [],
                "aircraft_profiles": [],
                "alerts": [],
                "anomalies": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
