"""Contract tests for Spiderweb's thin shared-runtime launcher adapter."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("prii_desktop")

from prii_desktop import DesktopConfig  # noqa: E402

from desktop import config, launch  # noqa: E402


def test_main_delegates_to_shared_runtime(monkeypatch):
    captured = []
    monkeypatch.setattr(launch, "launch", captured.append)

    launch.main()

    assert len(captured) == 1
    desktop_config = captured[0]
    assert isinstance(desktop_config, DesktopConfig)
    assert desktop_config.app_title == "Spiderweb"
    assert desktop_config.app_import == "desktop.app_server:app"
    assert desktop_config.repo_root == Path(config.REPO_ROOT)
    # The interface is the built SPA, so dist_dir points at the Vite output.
    assert desktop_config.dist_dir == Path(config.DIST_DIR)
    assert desktop_config.dist_dir == Path(config.FRONTEND_DIR) / "dist"

    # icon_path / attach_frontend only exist on prii_desktop >= 0.2.0. This repo
    # resolves thehub-pr by matching branch name and falls back to its main,
    # which still ships 0.1.0 — so assert them only when the field is there,
    # rather than failing every branch that builds against the older runtime.
    if hasattr(desktop_config, "icon_path"):
        assert desktop_config.icon_path == Path(config.ICON_PATH)
    if hasattr(desktop_config, "attach_frontend"):
        assert desktop_config.attach_frontend is True


def test_adapter_exports_only_its_entrypoint():
    legacy_helpers = {
        "display_url",
        "free_port",
        "running_instance_base",
        "wait_healthy",
        "write_lock",
    }
    assert legacy_helpers.isdisjoint(vars(launch))


def test_frozen_bundle_includes_layer_catalog():
    spec = (REPO_ROOT / "desktop" / "pyinstaller.spec").read_text(encoding="utf-8")

    assert 'REPO_ROOT / "configs" / "layer_catalog.yaml"' in spec
    assert '"configs"' in spec


def test_frozen_bundle_includes_seed_schema():
    spec = (REPO_ROOT / "desktop" / "pyinstaller.spec").read_text(encoding="utf-8")

    assert 'REPO_ROOT / "server" / "database" / "schema_sqlite.sql"' in spec
    assert '"server/database"' in spec
