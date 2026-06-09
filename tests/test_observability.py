"""Theme 10 — observability & robustness tests (T10-80/82/83/85/86)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


# ── T10-80 structured logging ────────────────────────────────────────────────

def test_json_formatter_emits_valid_json():
    from pipeline.logging_config import JsonFormatter

    rec = logging.makeLogRecord({
        "name": "x", "levelname": "INFO", "msg": "hello %s", "args": ("world",),
    })
    out = JsonFormatter().format(rec)
    obj = json.loads(out)
    assert obj["msg"] == "hello world"
    assert obj["level"] == "INFO"
    assert obj["logger"] == "x"
    assert "ts" in obj


def test_json_formatter_includes_extra_fields():
    from pipeline.logging_config import JsonFormatter

    rec = logging.makeLogRecord(
        {"name": "x", "levelname": "INFO", "msg": "m", "screenshot_id": 42}
    )
    obj = json.loads(JsonFormatter().format(rec))
    assert obj["screenshot_id"] == 42


def test_configure_logging_is_idempotent():
    from pipeline.logging_config import configure_logging

    configure_logging(level=logging.INFO)
    configure_logging(level=logging.DEBUG)
    managed = [h for h in logging.getLogger().handlers
               if getattr(h, "_spiderweb_managed", False)]
    assert len(managed) == 1  # repeat calls don't stack handlers


# ── T10-82 verbosity ─────────────────────────────────────────────────────────

def test_resolve_log_level_precedence():
    from pipeline.verbosity import resolve_log_level

    assert resolve_log_level(verbose=True) == logging.DEBUG
    assert resolve_log_level(quiet=True) == logging.WARNING
    assert resolve_log_level() == logging.INFO
    # verbose wins over quiet
    assert resolve_log_level(verbose=True, quiet=True) == logging.DEBUG


# ── T10-85 config loader ─────────────────────────────────────────────────────

def test_load_yaml_config_missing_raises(tmp_path):
    from pipeline.config_loader import ConfigError, load_yaml_config

    with pytest.raises(ConfigError):
        load_yaml_config(tmp_path / "nope.yaml")


def test_load_yaml_config_required_keys(tmp_path):
    from pipeline.config_loader import ConfigError, load_yaml_config

    p = tmp_path / "c.yaml"
    p.write_text("version: v1\nairports: []\n")
    cfg = load_yaml_config(p, required_keys=["version"])
    assert cfg["version"] == "v1"
    with pytest.raises(ConfigError):
        load_yaml_config(p, required_keys=["missing_key"])


def test_load_yaml_config_rejects_non_mapping(tmp_path):
    from pipeline.config_loader import ConfigError, load_yaml_config

    p = tmp_path / "list.yaml"
    p.write_text("- a\n- b\n")
    with pytest.raises(ConfigError):
        load_yaml_config(p)


def test_real_config_loads():
    """A shipped registry parses cleanly through the central loader."""
    from pipeline.config_loader import load_yaml_config

    cfg = load_yaml_config(REPO / "configs" / "airport_registry.yaml",
                           required_keys=["airports"])
    assert isinstance(cfg["airports"], list)


# ── T10-86 deterministic seeding ─────────────────────────────────────────────

def test_set_global_seed_makes_random_reproducible():
    import random

    from pipeline.seeding import set_global_seed

    set_global_seed(123)
    a = [random.random() for _ in range(5)]
    set_global_seed(123)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_set_global_seed_seeds_numpy():
    np = pytest.importorskip("numpy")
    from pipeline.seeding import set_global_seed

    set_global_seed(7)
    a = np.random.rand(4).tolist()
    set_global_seed(7)
    b = np.random.rand(4).tolist()
    assert a == b


# ── T10-83 server health (DB integrity) ──────────────────────────────────────

def test_health_endpoint_reports_integrity(tmp_path, monkeypatch):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from fastapi.testclient import TestClient

    import server.backend.main as backend

    # Point the app at a small valid sqlite DB.
    import sqlite3
    db = tmp_path / "priis.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(backend, "DB_PATH", db)

    with TestClient(backend.app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db_exists"] is True
    assert body["integrity_ok"] is True
    assert body["table_count"] >= 1
    assert body["status"] == "ok"


def test_health_endpoint_degraded_when_db_missing(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import server.backend.main as backend

    monkeypatch.setattr(backend, "DB_PATH", tmp_path / "absent.db")
    with TestClient(backend.app) as c:
        body = c.get("/health").json()
    assert body["status"] == "degraded"
    assert body["db_exists"] is False
