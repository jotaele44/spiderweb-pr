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

# Standalone dashboard and the data it reads.
DASHBOARD_DIR = REPO_ROOT / "dashboard"
OUTPUTS_DIR = REPO_ROOT / "outputs"
DASHBOARD_DATA = OUTPUTS_DIR / "dashboard_data.json"

# Default flight database consumed by run_all.py (may not exist; the export
# then produces an empty-but-valid snapshot and the dashboard shows source
# statuses instead of data).
DEFAULT_DB = Path.home() / "flight_database.db"

# Health endpoint used to detect that the server is up.
HEALTH_PATH = "/health"
