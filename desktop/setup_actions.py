"""Idempotent Spiderweb workspace preparation for the native setup UI.

Invoked by the shared desktop runtime via ``desktop/config.py::SETUP_ACTION``.

This used to export a ``dashboard_data.json`` snapshot of ``flights`` and
``aircraft_profiles`` for the standalone dashboard viewer. That viewer is gone
and the airspace surface is owned by skywatcher-pr (see
``docs/REPO_BOUNDARY.md``); the SPA reads the live backend instead. So setup now
prepares the two things the app actually needs: a writable exports directory to
serve at ``/outputs``, and a database for the backend to read.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where the backend looks for its database (server/backend/main.py::DB_PATH).
BACKEND_DB = REPO_ROOT / "server" / "priis.db"


def _workspace() -> Path:
    """The writable data home chosen by the setup UI, or the repo as a fallback."""
    configured = os.environ.get("SPIDERWEB_DATA_HOME", "").strip()
    return Path(configured) if configured else REPO_ROOT


def prepare_workspace() -> None:
    """Create the writable exports dir and seed a demo DB if none exists.

    Both steps are idempotent and non-fatal: the backend already degrades to
    empty-but-valid responses when ``priis.db`` is absent (and reports
    ``db_exists`` on ``/health``), so a read-only install directory must leave
    setup reporting success rather than raising.
    """
    (_workspace() / "exports").mkdir(parents=True, exist_ok=True)

    if BACKEND_DB.exists():
        return
    try:
        from server.ingestion import seed_demo

        seed_demo.main(BACKEND_DB)
    except Exception:
        # Read-only install, or the optional seed deps are unavailable. The app
        # still starts; the UI surfaces the empty state.
        return
