"""Desktop-wrapper configuration for this repo.

The desktop/ folder follows the shared PRII federation template; this is the one
genuinely per-repo file. The UI is the Vite single-page app under
``server/frontend``, served same-origin with the FastAPI backend so the app's
relative API calls (``/geo/*``, ``/contracts``, ``/rag/*``, ``/pipeline/*``)
resolve without CORS.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
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

# Database consumed by the desktop backend. Keep this binding identical to
# desktop.setup_actions and desktop.app_server so setup, diagnostics, and the
# live app cannot silently target different SQLite files.
_configured_data_home = os.environ.get(DATA_ENV_VAR, "").strip()
DEFAULT_DB = (
    Path(_configured_data_home) if _configured_data_home else REPO_ROOT
) / "server" / "priis.db"

# The frontend reads its API base from this scoped var (see
# server/frontend/src/config.ts); blank it at build time so a developer
# .env.local cannot point the desktop build at an external backend, and so the
# bundle stays same-origin against whichever ephemeral port the wrapper binds.
#
# The desktop app also runs desktop.app_server:app directly (see APP_IMPORT
# above), which is FastAPI's bare `main.app` — not the `production.py`
# wrapper that mounts the Martin tile-delivery router at /tiles. There is no
# Martin server process in a desktop install, so the municipios layer must
# use the GeoJSON delivery path (served by main.app's own /geo/*.geojson
# route) rather than the Martin-only default used by server deployments.
EXTRA_BUILD_ENV = {
    "VITE_API_BASE": "",
    "VITE_MUNICIPIOS_DELIVERY": "geojson",
}

# Health endpoint used to detect that the server is up.
HEALTH_PATH = "/health"


def _launchpad_status() -> list[dict[str, str]]:
    """Readiness rows for the Launch Pad. Runs before the backend exists, so it
    opens the database desktop/app_server.py will bind, read-only.
    """
    data_home = os.environ.get(DATA_ENV_VAR, "").strip()
    db_path = (Path(data_home) if data_home else REPO_ROOT) / "server" / "priis.db"
    counts: dict[str, int] = {}
    problem = ""
    if db_path.is_file():
        try:
            # mode=ro: a readiness check must never create or migrate the store.
            # as_uri() percent-encodes the path, so a "#" or "?" in a workspace
            # directory name is part of the file name, not URI syntax that would
            # cut off mode=ro and open some other file.
            uri = f"{db_path.resolve().as_uri()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                for table in ("contracts", "sites", "anomalies"):
                    counts[table] = int(
                        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
                    )
        except sqlite3.Error as exc:
            problem = str(exc)
    total = sum(counts.values())
    if problem:
        database = {
            "label": "Database",
            "value": "Unreadable",
            "status": "fail",
            "detail": (
                f"{db_path}: {problem}. Open Setup & Diagnostics and choose Repair."
            ),
        }
    elif not db_path.is_file():
        database = {
            "label": "Database",
            "value": "Missing",
            "status": "warn",
            "detail": (
                f"{db_path} does not exist yet, so the app would show built-in "
                "sample data. Open Setup & Diagnostics and choose Repair to seed it."
            ),
        }
    else:
        database = {
            "label": "Database",
            "value": "Empty" if not total else f"{total:,} records",
            "status": "pass" if total else "info",
            "detail": (
                f"{counts['contracts']:,} contracts, {counts['sites']:,} sites and "
                f"{counts['anomalies']:,} anomalies in {db_path}. A fresh workspace "
                "holds the diagnostic seed dataset until the pipeline is run."
            ),
        }
    layers = REPO_ROOT / "configs" / "layer_catalog.yaml"
    return [
        database,
        {
            "label": "Map layer catalog",
            "value": "Present" if layers.is_file() else "Missing",
            "status": "pass" if layers.is_file() else "fail",
            "detail": "configs/layer_catalog.yaml drives the Spatial module's layers.",
        },
    ]


# Pre-launch screen shown by the shared runtime (prii_desktop.launchpad).
#
# The API has no auth of its own. Guest refuses the routes that start or stop
# background jobs; Operator leaves the API exactly as it was. The app has no URL
# router (the six modules are in-memory tabs that always open on Command), so
# there is one start page.
LAUNCHPAD = {
    "tagline": "Spatial and operational intelligence for Puerto Rico",
    "summary": (
        "Spiderweb is the federation's spatial and operational producer: it "
        "links contracts, sites and anomalies to places and prepares the "
        "GIS-backed records TheHub aggregates. This is its diagnostic console."
    ),
    "highlights": ["Command", "Finance", "Spatial", "Anomaly", "Graph", "Query"],
    "status": _launchpad_status,
    "start_pages": [
        {
            "route": "/",
            "label": "Command Center",
            "description": (
                "Finance, Spatial, Anomaly, Graph and Query are tabs from here."
            ),
        },
    ],
    "guest": {
        "label": "Guest",
        "description": (
            "Read-only. Explore every module and ask questions in Query. "
            "Starting or stopping pipeline and indexing jobs is refused."
        ),
    },
    "operator": {
        "label": "Operator",
        "description": (
            "Full access from this computer, including running the data "
            "pipeline and rebuilding the query index."
        ),
    },
    # POST /rag/query answers a question and changes nothing, so a guest may use
    # it. The other three non-GET routes start or stop background jobs.
    "guest_guard": {"allow": ["POST /rag/query"]},
    "options": [
        {
            "id": "hf_token",
            "label": "Hugging Face token",
            "kind": "secret",
            "env": "HF_TOKEN",
            "help": (
                "Optional. Only used by the Query module, and only in a source "
                "checkout that has the RAG extras installed: it lets the local "
                "language model download a gated model from Hugging Face."
            ),
        },
    ],
}
