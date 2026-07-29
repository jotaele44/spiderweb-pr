"""Tests for the spiderweb desktop server.

The wrapper serves the built Vite SPA (server/frontend/dist) and the outputs/
exports from the same origin as the FastAPI backend, so the app's relative API
calls resolve without CORS. Skipped when fastapi/httpx aren't installed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

import desktop.app_server as app_server  # noqa: E402
from desktop import config  # noqa: E402


def test_desktop_health_ok():
    client = TestClient(app_server.app)
    r = client.get("/desktop/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "frontend_dist" in body and "frontend_index" in body


def test_backend_health_still_served():
    """The wrapper reuses the backend app, so its own /health must survive."""
    client = TestClient(app_server.app)
    assert client.get(config.HEALTH_PATH).status_code == 200


def test_api_route_not_shadowed_by_spa_mount():
    """The catch-all SPA mount must not shadow the backend's API routes."""
    client = TestClient(app_server.app)
    assert client.get("/catalog").status_code == 200


@pytest.mark.skipif(
    not (config.DIST_DIR / "index.html").is_file(),
    reason="frontend not built (run `npm run build` in server/frontend)",
)
def test_index_serves_built_spa():
    client = TestClient(app_server.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
