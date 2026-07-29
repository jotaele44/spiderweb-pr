# PyInstaller spec for the standalone desktop build (Phase 2).
# Build (on the target OS):
#   pip install pyinstaller
#   pyinstaller desktop/pyinstaller.spec --distpath dist-desktop
# Produces a self-contained one-folder app: dist-desktop/PRII-SPIDERWEB/
# The bundle mirrors the repo layout so desktop/app_server.py finds the built
# canonical GIS frontend, layer catalog, and optional spatial outputs.

import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "PRII-SPIDERWEB"

# Branding is generated from assets/branding/icon.png by
# thehub-pr/tools/build_program_icons.py, so the frozen build, the committed
# PRII-*.app bundle and the web favicons all trace back to one master.
BRANDING = REPO_ROOT / "assets" / "branding"
# PyInstaller wants .ico on Windows and .icns on macOS; it warns and ignores the
# argument on other platforms, so leave it unset there.
EXE_ICON = str(BRANDING / "icon.ico") if sys.platform == "win32" else None

# Windowed by default (no console window for double-click users). CI sets
# PRII_CONSOLE=1 to build a console binary it can smoke-test with visible stdio.
CONSOLE = os.environ.get("PRII_CONSOLE") == "1"

datas = [
    (str(REPO_ROOT / "server" / "frontend" / "dist"), "server/frontend/dist"),
    (str(REPO_ROOT / "configs" / "layer_catalog.yaml"), "configs"),
]
if (REPO_ROOT / "server" / "priis.db").exists():
    datas.append((str(REPO_ROOT / "server" / "priis.db"), "server"))
catalog = yaml.safe_load(
    (REPO_ROOT / "configs" / "layer_catalog.yaml").read_text(encoding="utf-8")
)
catalog_layers = {
    layer["layer_id"]
    for family in catalog.get("families", [])
    for layer in family.get("layers", [])
}
for folder in ("outputs", "data"):
    source_dir = REPO_ROOT / folder
    for layer_id in catalog_layers:
        geometry = source_dir / f"{layer_id}.geojson"
        if geometry.is_file():
            datas.append((str(geometry), folder))

a = Analysis(
    [str(REPO_ROOT / "desktop" / "launch.py")],
    pathex=[str(REPO_ROOT)],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "desktop.app_server",
        "server.backend.gis_app",
        "aiosqlite",
        "sse_starlette.sse",
        "yaml",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    console=CONSOLE,
    icon=EXE_ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(BRANDING / "AppIcon.icns"),
        bundle_identifier="pr.prii.spiderweb",
    )
