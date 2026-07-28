"""Contract tests for Spiderweb's thin shared-runtime desktop adapter.

Launcher behavior is tested once in thehub-pr/packages/prii_desktop. This file
keeps the producer boundary honest without requiring desktop-only dependencies
in Spiderweb's normal scientific test environment.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "desktop" / "launch.py"
CONFIG = REPO_ROOT / "desktop" / "config.py"


def test_launcher_is_a_thin_shared_runtime_adapter():
    source = LAUNCHER.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 40
    assert "from prii_desktop import DesktopConfig, launch" in source
    assert "launch(DesktopConfig.from_module(config))" in source
    assert "uvicorn" not in source
    assert "webview.create_window" not in source


def test_spiderweb_desktop_identity_and_custom_server_are_explicit():
    source = CONFIG.read_text(encoding="utf-8")

    assert 'APP_ID = "spiderweb"' in source
    assert 'APP_ACCENT = "#DC1606"' in source
    assert 'DESKTOP_APP_IMPORT = APP_IMPORT' in source
    assert 'FRONTEND_ENTRY = DASHBOARD_DIR / "dashboard.html"' in source
