"""Tests for the canonical Spiderweb GIS desktop server."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

import desktop.app_server as app_server  # noqa: E402


def test_health_ok():
    client = TestClient(app_server.app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert "db_exists" in body
    assert "db" in body


def test_index_serves_canonical_gis_html():
    if not app_server.FRONTEND_ENTRY.is_file():
        pytest.skip("canonical frontend has not been built")
    client = TestClient(app_server.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Spiderweb" in r.text
    assert "Spatial Intelligence" in r.text
    assert 'id="root"' in r.text


def test_missing_frontend_is_an_explicit_error(monkeypatch, tmp_path):
    missing = tmp_path / "missing.html"
    monkeypatch.setattr(app_server, "FRONTEND_ENTRY", missing)
    client = TestClient(app_server.app)
    r = client.get("/")
    assert r.status_code == 503
    assert "canonical frontend missing" in r.json()["detail"]
