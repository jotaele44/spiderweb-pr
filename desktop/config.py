"""Desktop-wrapper configuration for this repo.

The desktop/ folder follows the shared PRII federation template, adapted for
spiderweb-pr: the UI is the Vite single-page app under ``server/frontend``,
served from the same origin as the FastAPI backend so its relative API calls
resolve without CORS.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Window title of the desktop app.
APP_TITLE = "Spiderweb"

# Dotted import path of the FastAPI application object serving the API.
APP_IMPORT = "server.backend.main:app"

# Directory containing the Vite frontend (with package.json).
FRONTEND_DIR = REPO_ROOT / "server" / "frontend"

# Vite build output served by the desktop app.
DIST_DIR = FRONTEND_DIR / "dist"

# JSON exports mounted read-only at /outputs for the app to fetch.
OUTPUTS_DIR = REPO_ROOT / "outputs"

# Default flight database consumed by run_all.py (may not exist; the backend
# then serves empty-but-valid responses and the app shows source statuses
# instead of data).
DEFAULT_DB = Path.home() / "flight_database.db"

# The frontend reads its API base from this scoped var (see
# server/frontend/src/config.ts); blank it at build time so a developer
# .env.local cannot point the desktop build at an external backend.
EXTRA_BUILD_ENV = {
    "VITE_API_BASE": "",
}

# Health endpoint used to detect that the server is up.
HEALTH_PATH = "/health"
