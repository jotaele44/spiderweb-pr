"""Same-origin API and canonical GIS frontend for the Spiderweb desktop app."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from desktop.config import FRONTEND_DIR, FRONTEND_ENTRY  # noqa: E402
from server.backend.gis_app import app  # noqa: E402

assets = FRONTEND_DIR / "assets"
if assets.is_dir():
    app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")


def require_frontend() -> None:
    """Fail explicitly when a source checkout has not built the canonical UI."""
    if not FRONTEND_ENTRY.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"canonical frontend missing at {FRONTEND_ENTRY}; "
                "run npm ci && npm run build in server/frontend"
            ),
        )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    require_frontend()
    return FileResponse(FRONTEND_ENTRY)


@app.get("/{client_path:path}", include_in_schema=False)
async def spa_fallback(client_path: str) -> FileResponse:
    require_frontend()
    candidate = (FRONTEND_DIR / client_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIR.resolve())
    except ValueError:
        return FileResponse(FRONTEND_ENTRY)
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(FRONTEND_ENTRY)
