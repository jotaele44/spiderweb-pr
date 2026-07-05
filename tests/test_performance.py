"""Tests for Theme 4 performance improvements (T4-25, T4-26, T4-27, T4-33, T4-34)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


# ── T4-27: WAL + db_utils ────────────────────────────────────────────────────

def test_configure_connection_sets_wal(tmp_path):
    from pipeline.db_utils import configure_connection

    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    configure_connection(conn)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


def test_configure_connection_sets_cache_size(tmp_path):
    from pipeline.db_utils import configure_connection

    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    configure_connection(conn)
    cache = conn.execute("PRAGMA cache_size").fetchone()[0]
    conn.close()
    assert cache == -32000


def test_configure_connection_idempotent(tmp_path):
    from pipeline.db_utils import configure_connection

    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    configure_connection(conn)
    configure_connection(conn)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


# ── T4-25: flight DB indexes ─────────────────────────────────────────────────

def test_flight_db_has_origin_and_dest_indexes(tmp_path):
    from pipeline.flight_analyzer import FlightDatabase

    db_path = str(tmp_path / "flights.db")
    FlightDatabase(db_path)  # triggers _init_tables

    conn = sqlite3.connect(db_path)
    indexes = {
        row[1]
        for row in conn.execute("PRAGMA index_list('flights')").fetchall()
    }
    conn.close()
    assert "idx_flights_origin" in indexes
    assert "idx_flights_dest" in indexes
    assert "idx_flights_mission" in indexes


def test_flight_db_has_screenshot_confidence_index(tmp_path):
    from pipeline.flight_analyzer import FlightDatabase

    db_path = str(tmp_path / "flights.db")
    FlightDatabase(db_path)

    conn = sqlite3.connect(db_path)
    indexes = {
        row[1]
        for row in conn.execute("PRAGMA index_list('screenshots')").fetchall()
    }
    conn.close()
    assert "idx_screenshots_conf" in indexes


def test_flight_db_has_track_coords_index(tmp_path):
    from pipeline.flight_analyzer import FlightDatabase

    db_path = str(tmp_path / "flights.db")
    FlightDatabase(db_path)

    conn = sqlite3.connect(db_path)
    indexes = {
        row[1]
        for row in conn.execute("PRAGMA index_list('track_points')").fetchall()
    }
    conn.close()
    assert "idx_track_coords" in indexes


# ── T4-33: mbil_class LRU cache ──────────────────────────────────────────────

def test_mbil_class_is_cached():
    from integration.mbil import mbil_class

    mbil_class.cache_clear()
    mbil_class(18.4655, -66.1057)
    info = mbil_class.cache_info()
    assert info.currsize >= 1


def test_mbil_class_cache_hit_on_repeat():
    from integration.mbil import mbil_class

    mbil_class.cache_clear()
    mbil_class(18.4655, -66.1057)
    mbil_class(18.4655, -66.1057)
    info = mbil_class.cache_info()
    assert info.hits >= 1


def test_mbil_class_cache_returns_same_result():
    from integration.mbil import mbil_class

    mbil_class.cache_clear()
    r1 = mbil_class(18.4655, -66.1057)
    r2 = mbil_class(18.4655, -66.1057)
    assert r1 == r2


def test_mbil_class_cache_max_size_is_set():
    from integration.mbil import mbil_class

    assert mbil_class.cache_info().maxsize == 4096


# ── T4-34: per-stage elapsed_sec in release_check ────────────────────────────

def test_release_check_stages_have_elapsed_sec(tmp_path):
    from release_check import ReleaseCheck

    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="normal", run_tests=False)
    report = rc.run()

    timed_stages = [
        "syntax_check", "validate", "export_pr_intel",
        "export_spiderweb", "earthgpt_selftest",
    ]
    for stage in timed_stages:
        assert "elapsed_sec" in report[stage], f"elapsed_sec missing in {stage}"
        assert isinstance(report[stage]["elapsed_sec"], float), (
            f"elapsed_sec should be float in {stage}"
        )
        assert report[stage]["elapsed_sec"] >= 0.0


def test_release_check_skipped_core_tests_has_elapsed_zero(tmp_path):
    from release_check import ReleaseCheck

    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(tmp_path / "out"),
                      mode="normal", run_tests=False)
    report = rc.run()
    assert report["core_tests"]["elapsed_sec"] == 0.0


def test_release_check_elapsed_sec_preserved_in_json(tmp_path):
    from release_check import ReleaseCheck

    out_dir = tmp_path / "out"
    rc = ReleaseCheck(str(tmp_path / "nope.db"), str(out_dir),
                      mode="normal", run_tests=False)
    rc.run()

    on_disk = json.loads((out_dir / "release_report.json").read_text())
    assert "elapsed_sec" in on_disk["syntax_check"]


# ── T4-26: store_flight batches track-point inserts (executemany) ─────────────

def _make_flight_record(n_track_points: int = 3):
    from pipeline.flight_analyzer import FlightRecord

    return FlightRecord(
        flight_id="FL-TEST-1",
        callsign="N123PR",
        aircraft_type="C172",
        operator="Test Op",
        origin_airport="TJSJ",
        destination_airport="TJBQ",
        origin_lat=18.44, origin_lon=-66.00,
        dest_lat=18.50, dest_lon=-67.13,
        takeoff_time="2024-03-15T08:00:00",
        landing_time="2024-03-15T08:45:00",
        flight_duration_minutes=45,
        max_altitude_ft=4500,
        avg_speed_mph=120.0,
        mission_type="patrol",
        num_screenshots=2,
        track_points=[
            {
                "timestamp": f"2024-03-15T08:{i:02d}:00",
                "latitude": 18.40 + i * 0.01,
                "longitude": -66.10 - i * 0.01,
                "altitude_ft": 3000 + i * 100,
                "ground_speed_mph": 110 + i,
            }
            for i in range(n_track_points)
        ],
    )


def test_store_flight_persists_all_track_points(tmp_path):
    from pipeline.flight_analyzer import FlightDatabase

    db_path = str(tmp_path / "flights.db")
    record = _make_flight_record(n_track_points=3)
    FlightDatabase(db_path).store_flight(record)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = conn.execute(
        "SELECT COUNT(*) FROM track_points WHERE flight_id = ?", (record.flight_id,)
    ).fetchone()[0]
    first = conn.execute(
        "SELECT latitude, longitude, ground_speed_mph FROM track_points "
        "WHERE flight_id = ? ORDER BY id LIMIT 1",
        (record.flight_id,),
    ).fetchone()
    conn.close()

    assert count == 3
    expected = record.track_points[0]
    assert first["latitude"] == expected["latitude"]
    assert first["longitude"] == expected["longitude"]
    assert first["ground_speed_mph"] == expected["ground_speed_mph"]


def test_store_flight_with_no_track_points(tmp_path):
    # executemany over an empty list must be a clean no-op (flight still stored).
    from pipeline.flight_analyzer import FlightDatabase

    db_path = str(tmp_path / "flights.db")
    FlightDatabase(db_path).store_flight(_make_flight_record(n_track_points=0))

    conn = sqlite3.connect(db_path)
    track_count = conn.execute("SELECT COUNT(*) FROM track_points").fetchone()[0]
    flight_count = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
    conn.close()
    assert track_count == 0
    assert flight_count == 1


# ── T4-25: PRIIS server schema events(kind) index + migration ─────────────────

PRIIS_SCHEMA = Path(__file__).parent.parent / "server" / "database" / "schema_sqlite.sql"


def test_priis_schema_has_events_kind_index():
    conn = sqlite3.connect(":memory:")
    conn.executescript(PRIIS_SCHEMA.read_text())
    indexes = {row[1] for row in conn.execute("PRAGMA index_list('events')").fetchall()}
    conn.close()
    assert "idx_events_kind" in indexes


def test_migration_adds_events_kind_index_to_existing_db():
    from server.ingestion.migrations import ensure_performance_indexes

    # Simulate an existing DB that has an events table but no perf indexes.
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE events (id TEXT PRIMARY KEY, kind TEXT NOT NULL, at TEXT)")

    def has_index():
        return "idx_events_kind" in {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }

    assert not has_index()
    added = ensure_performance_indexes(conn)
    assert added["idx_events_kind"] is True
    assert has_index()

    # Idempotent: a second run reports nothing newly created.
    again = ensure_performance_indexes(conn)
    conn.close()
    assert again["idx_events_kind"] is False
