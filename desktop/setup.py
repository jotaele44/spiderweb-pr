"""Idempotent source-checkout setup for the Spiderweb desktop application."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.config import FRONTEND_ENTRY, REPO_ROOT  # noqa: E402

VENV_DIR = REPO_ROOT / ".venv"
MARKER = Path(__file__).resolve().parent / ".setup-complete"
MIN_PYTHON = (3, 10)
REQUIREMENTS = REPO_ROOT / "requirements-desktop.txt"
FRONTEND_DIR = REPO_ROOT / "server" / "frontend"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(command: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def is_complete() -> bool:
    return MARKER.exists() and venv_python().exists() and FRONTEND_ENTRY.exists()


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


def build_frontend() -> None:
    if FRONTEND_ENTRY.exists():
        return
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit(
            "The canonical frontend is not built and npm is unavailable. "
            "Use a packaged Spiderweb release or install Node.js for source development."
        )
    run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR)
    run([npm, "run", "build"], cwd=FRONTEND_DIR)


def main() -> None:
    arguments = set(sys.argv[1:])
    if "--force" in arguments:
        MARKER.unlink(missing_ok=True)
    if is_complete():
        if "--ensure" not in arguments:
            print("Setup already complete (use --force to redo).")
        return
    setup_python()
    build_frontend()
    MARKER.write_text("ok\n", encoding="utf-8")
    print("Desktop setup complete.")


if __name__ == "__main__":
    main()
