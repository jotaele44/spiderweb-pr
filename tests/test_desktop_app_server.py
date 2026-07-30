"""Tests for the spiderweb desktop server.

``desktop/app_server.py`` is a thin repository adapter: it exposes the real
FastAPI backend with the writable exports mounted, and the shared
``prii_desktop`` runtime attaches the built SPA on top via
``desktop/config.py::APP_IMPORT``.

The composed app is built once at import time, before any TestClient exists:
``attach_spa`` installs middleware, and Starlette refuses to add middleware to an
app that has already started — so composing lazily inside a test would fail
depending on test order. Skipped when fastapi/httpx aren't installed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("prii_desktop")

from prii_desktop import DesktopConfig, make_desktop_app  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from desktop import config  # noqa: E402

# The app exactly as the desktop wrapper serves it: backend + /outputs + SPA.
DESKTOP_APP = make_desktop_app(DesktopConfig.from_module(config))


def test_desktop_health_ok():
    client = TestClient(DESKTOP_APP)
    r = client.get("/desktop/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "frontend_dist" in body and "frontend_index" in body


def test_backend_health_still_served():
    """The wrapper reuses the backend app, so its own /health must survive."""
    client = TestClient(DESKTOP_APP)
    assert client.get(config.HEALTH_PATH).status_code == 200


def test_api_route_not_shadowed_by_spa_mount():
    """The catch-all SPA fallback must not shadow the backend's API routes."""
    client = TestClient(DESKTOP_APP)
    assert client.get("/catalog").status_code == 200


def test_outputs_mount_precedes_spa_catch_all(tmp_path):
    """An export under /outputs must be served, not swallowed by the SPA.

    The SPA fallback is a catch-all registered when the runtime attaches the SPA,
    so the adapter has to mount /outputs first — a regression here would serve
    index.html for every export the app fetches, which reads as an empty UI
    rather than an error.
    """
    import desktop.app_server as app_server

    probe = app_server.OUTPUTS_DIR / "desktop_mount_probe.json"
    probe.write_text('{"probe": true}\n', encoding="utf-8")
    try:
        r = TestClient(DESKTOP_APP).get(f"/outputs/{probe.name}")
        assert r.status_code == 200
        assert r.json() == {"probe": True}
    finally:
        probe.unlink(missing_ok=True)


@pytest.mark.skipif(
    not (config.DIST_DIR / "index.html").is_file(),
    reason="frontend not built (run `npm run build` in server/frontend)",
)
def test_index_serves_built_spa():
    client = TestClient(DESKTOP_APP)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
