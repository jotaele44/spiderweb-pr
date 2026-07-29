"""Same-origin ASGI app for the spiderweb-pr desktop wrapper.

Serves the standalone dashboard (dashboard/dashboard.html + vendored JS) and
the JSON exports under outputs/ from one local port, replacing the
"python -m http.server 8080" step from the dashboard header docs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from prii_desktop import DesktopConfig, desktop_controls_script  # noqa: E402

from desktop import config  # noqa: E402
from desktop.config import DASHBOARD_DIR  # noqa: E402

_workspace = os.environ.get("SPIDERWEB_DATA_HOME", "").strip()
OUTPUTS_DIR = (
    Path(_workspace) / "exports"
    if _workspace
    else config.REPO_ROOT / "outputs"
)
DASHBOARD_DATA = OUTPUTS_DIR / "dashboard_data.json"
_desktop_config = DesktopConfig.from_module(config)

app = FastAPI(title="Spiderweb Dashboard Server")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "dashboard": (DASHBOARD_DIR / "dashboard.html").is_file(),
        "dashboard_data": DASHBOARD_DATA.is_file(),
    }


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    document = (DASHBOARD_DIR / "dashboard.html").read_text(encoding="utf-8")
    control = desktop_controls_script(_desktop_config)
    document = document.replace("</body>", f"{control}</body>", 1)
    return HTMLResponse(document)


OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
