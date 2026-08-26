"""
migrations.py — Idempotent SQLite migrations for priis.db.

Each migration helper takes a live sqlite3.Connection and is safe to call any
number of times. They introspect the schema via PRAGMA table_info, since
SQLite's ADD COLUMN does not support an IF NOT EXISTS clause across all
versions shipped with macOS.

Call these from anywhere that opens a priis.db connection: seed_demo.py,
ingest_tiger_pr.py, and the FastAPI lifespan hook in server/backend/main.py.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Iterable

log = logging.getLogger(__name__)


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    column_type: str,
) -> bool:
    """Return True if the column was added on this call."""
    existing = _existing_columns(conn, table)
    if column in existing:
        return False
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        log.info("migration: added %s.%s %s", table, column, column_type)
        return True
    except sqlite3.OperationalError as exc:
        # Race condition with a concurrent migrator, or the column was added
        # between our PRAGMA check and the ALTER. Re-check; suppress only if
        # the column now exists.
        if column in _existing_columns(conn, table):
            return False
        raise RuntimeError(
            f"failed to add {table}.{column}: {exc}"
        ) from exc


def ensure_sites_geoid_columns(conn: sqlite3.Connection) -> dict[str, bool]:
    """
    Add municipio_geoid + tract_geoid TEXT columns to the sites table if absent.

    Returns a dict mapping column name → True if it was added on this call,
    False if it was already present. Callers may log this for observability.
    """
    if "sites" not in _existing_tables(conn):
        # Fresh DB — schema_sqlite.sql will be applied separately. Nothing to
        # migrate yet; the schema file itself already defines the columns.
        return {"municipio_geoid": False, "tract_geoid": False, "zcta_geoid": False}
    added = {
        "municipio_geoid": _add_column_if_missing(
            conn, "sites", "municipio_geoid", "TEXT"
        ),
        "tract_geoid": _add_column_if_missing(
            conn, "sites", "tract_geoid", "TEXT"
        ),
        "zcta_geoid": _add_column_if_missing(
            conn, "sites", "zcta_geoid", "TEXT"
        ),
    }
    conn.commit()
    return added


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    return {row[0] for row in cur.fetchall()}



def _existing_indexes(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    return {row[0] for row in cur.fetchall()}


def ensure_performance_indexes(conn: sqlite3.Connection) -> dict[str, bool]:
    """
    Create hot-path indexes if absent. Idempotent (CREATE INDEX IF NOT EXISTS),
    so safe on every startup. Keep in sync with server/database/schema_sqlite.sql.

    - idx_events_kind: ``/events`` consumers filter ``events WHERE kind=?``;
      without this index that query full-scans the events table.

    Returns a dict mapping index name → True if it was created on this call.
    """
    if "events" not in _existing_tables(conn):
        # Fresh DB — schema_sqlite.sql already defines the index.
        return {"idx_events_kind": False}
    existed = "idx_events_kind" in _existing_indexes(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)")
    conn.commit()
    return {"idx_events_kind": not existed}


def run_all(conn: sqlite3.Connection) -> dict[str, dict]:
    """Run every registered migration. Safe to call on every startup."""
    return {
        "sites_geoid": ensure_sites_geoid_columns(conn),
        "performance_indexes": ensure_performance_indexes(conn),
    }


__all__ = [
    "ensure_sites_geoid_columns",
    "ensure_performance_indexes",
    "run_all",
]
