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
