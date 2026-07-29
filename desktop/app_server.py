"""Same-origin ASGI app for the spiderweb-pr desktop wrapper.

Serves the built Vite single-page app (``server/frontend/dist``) and the JSON
exports under ``outputs/`` from the same port as the FastAPI backend, so the
app's relative API calls (``/geo/*``, ``/contracts``, ``/rag/*``,
``/pipeline/*``) resolve without CORS or a second process.

The backend's API routes are registered before the catch-all static mount
below, so they keep taking precedence over the SPA fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.staticfiles import StaticFiles  # noqa: E402

from desktop.config import DIST_DIR, OUTPUTS_DIR  # noqa: E402
from server.backend.main import app  # noqa: E402


@app.get("/desktop/health", include_in_schema=False)
def desktop_health() -> dict:
    """Desktop-wrapper readiness, distinct from the backend's own /health."""
    return {
        "status": "ok",
        "frontend_dist": DIST_DIR.is_dir(),
        "frontend_index": (DIST_DIR / "index.html").is_file(),
        "outputs": OUTPUTS_DIR.is_dir(),
    }


OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")

# Mounted last so it only handles paths no API route claimed. Absent before the
# first `npm run build`; the wrapper still serves the API in that state rather
# than failing to import.
if (DIST_DIR / "index.html").is_file():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
