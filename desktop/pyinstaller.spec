# PyInstaller spec for the standalone desktop build (Phase 2).
# Build (on the target OS):
#   pip install pyinstaller
#   pyinstaller desktop/pyinstaller.spec --distpath dist-desktop
# Produces a self-contained one-folder app: dist-desktop/PRII-SPIDERWEB/
# The bundle mirrors the repo layout so desktop/app_server.py finds dashboard/
# and outputs/ with its normal relative paths (no Vite build — the UI is the
# standalone dashboard/dashboard.html viewer with vendored JS).

import os
import sys
from pathlib import Path

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
    (str(REPO_ROOT / "dashboard"), "dashboard"),
    (str(BRANDING / "icon-256.png"), "assets/branding"),
]
if (REPO_ROOT / "outputs").exists():
    datas.append((str(REPO_ROOT / "outputs"), "outputs"))

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
        "desktop.setup_actions",
        "prii_desktop",
        "prii_desktop.launcher",
        "prii_desktop.appserver",
        "prii_desktop.config",
        "prii_desktop.setup_center",
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
        info_plist={
            "CFBundleDisplayName": "Spiderweb",
            "CFBundleName": "Spiderweb",
        },
    )
