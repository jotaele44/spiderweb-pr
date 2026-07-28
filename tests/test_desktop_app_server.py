"""Tests for the spiderweb desktop server (serves the standalone dashboard).

Unlike the SPA repos, spiderweb's desktop app serves dashboard/dashboard.html
plus the outputs/ exports statically. Skipped when fastapi/httpx aren't installed.
"""

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
    assert body["status"] == "ok"
    assert "dashboard" in body and "dashboard_data" in body


def test_index_serves_dashboard_html():
    client = TestClient(app_server.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_setup_selected_outputs_are_resolved_after_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PRII_SPIDERWEB_DATA_HOME", str(tmp_path))
    assert app_server._mutable_outputs_dir() == tmp_path / "outputs"
