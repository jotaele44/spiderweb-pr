"""Repository adapter for the shared PRII desktop runtime.

The shared runtime (``prii_desktop``) imports this module's ``app`` via
``desktop/config.py::APP_IMPORT``, then attaches the built SPA from ``DIST_DIR``
on top of it. So this file's only job is to expose the real FastAPI backend with
Spiderweb's writable exports mounted — the SPA, its fallback routing and the
missing-build page all come from the shared runtime.

Mount order matters: the runtime's SPA fallback is a catch-all ``GET
/{full_path:path}``, so ``/outputs`` has to be mounted here (before that call)
rather than afterwards.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.staticfiles import StaticFiles  # noqa: E402

from desktop import config  # noqa: E402
from server.backend.main import app  # noqa: E402

# Honour the workspace the setup UI picked, so a read-only install directory
# still gets writable exports (see desktop/setup_actions.py).
_workspace = os.environ.get(config.DATA_ENV_VAR, "").strip()
OUTPUTS_DIR = Path(_workspace) / "exports" if _workspace else config.OUTPUTS_DIR


@app.get("/desktop/health", include_in_schema=False)
def desktop_health() -> dict:
    """Desktop-wrapper readiness, distinct from the backend's own /health."""
    return {
        "status": "ok",
        "frontend_dist": config.DIST_DIR.is_dir(),
        "frontend_index": (config.DIST_DIR / "index.html").is_file(),
        "outputs": OUTPUTS_DIR.is_dir(),
        "workspace": _workspace or None,
    }


OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
