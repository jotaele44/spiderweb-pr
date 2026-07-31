"""One-time setup for the spiderweb-pr desktop wrapper (stdlib only).

Creates a private .venv with the small server dependencies and builds the Vite
single-page app under server/frontend, which the wrapper then serves from the
same origin as the backend. Node/npm is required for that build.

Usage:
  python desktop/setup.py            run setup (skips when already complete)
  python desktop/setup.py --ensure   quiet fast-path used by the launchers
  python desktop/setup.py --force    redo setup from scratch
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.config import (  # noqa: E402
    DIST_DIR,
    EXTRA_BUILD_ENV,
    FRONTEND_DIR,
    REPO_ROOT,
)

VENV_DIR = REPO_ROOT / ".venv"
MARKER = Path(__file__).resolve().parent / ".setup-complete"
MIN_PYTHON = (3, 10)

REQUIREMENTS = REPO_ROOT / "requirements-desktop.txt"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def is_complete() -> bool:
    return (
        MARKER.exists()
        and venv_python().exists()
        and (DIST_DIR / "index.html").is_file()
    )


def setup_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(f"Python 3.10+ required, found {sys.version.split()[0]}")
    if not venv_python().exists():
        print(f"Creating virtual environment at {VENV_DIR} …")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)
    run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    run(
        [str(venv_python()), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)]
    )


def npm_command() -> str:
    """npm is a .cmd shim on Windows, which subprocess needs spelled out."""
    return "npm.cmd" if os.name == "nt" else "npm"


def build_frontend() -> None:
    """Install and build the SPA that the wrapper serves."""
    npm = npm_command()
    if not shutil.which(npm):
        raise SystemExit(
            "Node.js/npm is required to build the desktop UI "
            f"({FRONTEND_DIR.relative_to(REPO_ROOT)}). Install Node 22+ and re-run."
        )
    lock = FRONTEND_DIR / "package-lock.json"
    run([npm, "ci" if lock.exists() else "install", "--no-audit", "--no-fund"],
        cwd=FRONTEND_DIR)
    # Blank the API base so the bundle talks to whichever port the wrapper binds.
    env = {**os.environ, **EXTRA_BUILD_ENV}
    run([npm, "run", "build"], cwd=FRONTEND_DIR, env=env)


def main() -> None:
    args = set(sys.argv[1:])
    if "--force" in args:
        MARKER.unlink(missing_ok=True)
    if is_complete():
        if "--ensure" not in args:
            print("Setup already complete (use --force to redo).")
        return
    setup_python()
    build_frontend()
    MARKER.write_text("ok\n", encoding="utf-8")
    print("Desktop setup complete.")


if __name__ == "__main__":
    main()
