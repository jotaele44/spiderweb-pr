"""Tests for Theme 4 performance improvements (T4-25, T4-26, T4-27, T4-33, T4-34)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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
