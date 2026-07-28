"""Same-origin ASGI app for the spiderweb-pr desktop wrapper.

Serves the standalone dashboard (dashboard/dashboard.html + vendored JS) and
the JSON exports under outputs/ from one local port, replacing the
"python -m http.server 8080" step from the dashboard header docs.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from desktop.config import BUNDLED_OUTPUTS_DIR, DASHBOARD_DIR  # noqa: E402

app = FastAPI(title="Spiderweb Dashboard Server")


def _mutable_outputs_dir() -> Path:
    """Resolve setup-selected storage after the shared runtime sets its env."""
    data_home = os.environ.get("PRII_SPIDERWEB_DATA_HOME")
    return Path(data_home) / "outputs" if data_home else BUNDLED_OUTPUTS_DIR


OUTPUTS_DIR = _mutable_outputs_dir()
DASHBOARD_DATA = OUTPUTS_DIR / "dashboard_data.json"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dashboard": (DASHBOARD_DIR / "dashboard.html").is_file(),
        "dashboard_data": DASHBOARD_DATA.is_file(),
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "dashboard.html")


if OUTPUTS_DIR != BUNDLED_OUTPUTS_DIR and BUNDLED_OUTPUTS_DIR.is_dir():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    for source in BUNDLED_OUTPUTS_DIR.iterdir():
        destination = OUTPUTS_DIR / source.name
        if destination.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
