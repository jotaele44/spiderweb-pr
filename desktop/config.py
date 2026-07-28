"""Desktop-wrapper configuration for this repo.

The desktop/ folder follows the shared PRII federation template, adapted for
spiderweb-pr: the UI is the standalone dashboard/dashboard.html viewer (no
build step) reading JSON exports from outputs/.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Window title of the desktop app.
APP_TITLE = "Spiderweb"
APP_ID = "spiderweb"
APP_ACCENT = "#DC1606"
APP_ICON = REPO_ROOT / "assets" / "branding" / "icon-256.png"
RELEASES_URL = "https://github.com/jotaele44/spiderweb-pr/releases"
SETUP_VERSION = 1

# Standalone dashboard and the data it reads.
DASHBOARD_DIR = REPO_ROOT / "dashboard"
BUNDLED_OUTPUTS_DIR = REPO_ROOT / "outputs"
_DATA_HOME = os.environ.get("PRII_SPIDERWEB_DATA_HOME")
OUTPUTS_DIR = (
    Path(_DATA_HOME) / "outputs"
    if _DATA_HOME
    else BUNDLED_OUTPUTS_DIR
)
DASHBOARD_DATA = OUTPUTS_DIR / "dashboard_data.json"
DIST_DIR = DASHBOARD_DIR
FRONTEND_ENTRY = DASHBOARD_DIR / "dashboard.html"

# Spiderweb assembles its dashboard and JSON-export routes itself. The shared
# runtime still owns native setup, diagnostics, single-instance, and lifecycle.
APP_IMPORT = "desktop.app_server:app"
DESKTOP_APP_IMPORT = APP_IMPORT

# Default flight database consumed by run_all.py (may not exist; the export
# then produces an empty-but-valid snapshot and the dashboard shows source
# statuses instead of data).
DEFAULT_DB = Path.home() / "flight_database.db"

# Health endpoint used to detect that the server is up.
HEALTH_PATH = "/health"
