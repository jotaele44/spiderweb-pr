"""Desktop-wrapper configuration for this repo.

The desktop/ folder follows the shared PRII federation template; this is the one
genuinely per-repo file. The UI is the Vite single-page app under
``server/frontend``, served same-origin with the FastAPI backend so the app's
relative API calls (``/geo/*``, ``/contracts``, ``/rag/*``, ``/pipeline/*``)
resolve without CORS.
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

# Dotted import path of the FastAPI app object. The shared runtime imports this,
# then attaches the SPA from DIST_DIR on top of it — so this adapter must be what
# mounts /outputs, otherwise the SPA's catch-all route would claim it first.
APP_IMPORT = "desktop.app_server:app"

# The interface is now a built SPA rather than the previous no-build dashboard,
# so the shared launcher does attach a frontend.
ATTACH_FRONTEND = True

# Directory containing the Vite frontend (with package.json), and its build
# output — DIST_DIR is what DesktopConfig.from_module reads.
FRONTEND_DIR = REPO_ROOT / "server" / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

# JSON exports mounted read-only at /outputs.
OUTPUTS_DIR = REPO_ROOT / "outputs"

# Default flight database consumed by run_all.py (may not exist; the backend
# then serves empty-but-valid responses and the app shows source statuses
# instead of data).
DEFAULT_DB = Path.home() / "flight_database.db"

# The frontend reads its API base from this scoped var (see
# server/frontend/src/config.ts); blank it at build time so a developer
# .env.local cannot point the desktop build at an external backend, and so the
# bundle stays same-origin against whichever ephemeral port the wrapper binds.
EXTRA_BUILD_ENV = {
    "VITE_API_BASE": "",
}

# Health endpoint used to detect that the server is up.
HEALTH_PATH = "/health"
