"""Contract tests for Spiderweb's thin shared-runtime launcher adapter."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    assert desktop_config.dist_dir == Path(config.DIST_DIR)
    assert desktop_config.icon_path == Path(config.ICON_PATH)
    assert desktop_config.attach_frontend is False


def test_adapter_exports_only_its_entrypoint():
    legacy_helpers = {
        "display_url",
        "free_port",
        "running_instance_base",
        "wait_healthy",
        "write_lock",
    }
    assert legacy_helpers.isdisjoint(vars(launch))
