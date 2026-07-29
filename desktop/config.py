"""Desktop-wrapper configuration for this repo.

The desktop/ folder follows the shared PRII federation template, adapted for
spiderweb-pr: the UI is the standalone dashboard/dashboard.html viewer (no
build step) reading JSON exports from outputs/.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Window title of the desktop app.
APP_TITLE = "Spiderweb"
APP_ID = "Spiderweb"
BRAND_ACCENT = "#ca0c02"
BRAND_ACCENT_STRONG = "#9f0a02"
ICON_PATH = REPO_ROOT / "assets" / "branding" / "icon-256.png"
SETUP_VERSION = 1
DATA_ENV_VAR = "SPIDERWEB_DATA_HOME"
SETUP_ACTION = "desktop.setup_actions:prepare_workspace"

# The shared launcher imports this small repository adapter. It already mounts
# Spiderweb's no-build dashboard and writable exports, so no SPA attachment is
# needed.
APP_IMPORT = "desktop.app_server:app"
ATTACH_FRONTEND = False

# Standalone dashboard and the data it reads.
DASHBOARD_DIR = REPO_ROOT / "dashboard"
OUTPUTS_DIR = REPO_ROOT / "outputs"
DASHBOARD_DATA = OUTPUTS_DIR / "dashboard_data.json"

# Shared-runtime compatibility: this is the bundled, no-build interface root.
DIST_DIR = DASHBOARD_DIR

# Default flight database consumed by run_all.py (may not exist; the export
# then produces an empty-but-valid snapshot and the dashboard shows source
# statuses instead of data).
DEFAULT_DB = Path.home() / "flight_database.db"

# Health endpoint used to detect that the server is up.
HEALTH_PATH = "/health"
