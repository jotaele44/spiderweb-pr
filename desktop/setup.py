"""One-time setup for the spiderweb-pr desktop wrapper (stdlib only).

Creates a private .venv with the small server dependencies and produces a
dashboard data snapshot from the local flight database via run_all.py
--export-json (an empty-but-valid snapshot when no database exists). No
Node/npm build is needed: the dashboard is the standalone
dashboard/dashboard.html viewer with vendored JS.

Usage:
  python desktop/setup.py            run setup (skips when already complete)
  python desktop/setup.py --ensure   quiet fast-path used by the launchers
  python desktop/setup.py --force    redo setup from scratch
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.config import DASHBOARD_DATA, DEFAULT_DB, REPO_ROOT  # noqa: E402

VENV_DIR = REPO_ROOT / ".venv"
MARKER = Path(__file__).resolve().parent / ".setup-complete"
MIN_PYTHON = (3, 10)

REQUIREMENTS = REPO_ROOT / "requirements-desktop.txt"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def is_complete() -> bool:
    return MARKER.exists() and venv_python().exists() and DASHBOARD_DATA.exists()


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


def export_dashboard_data() -> None:
    """Snapshot the local flight DB for the dashboard (empty DB → empty snapshot)."""
    DASHBOARD_DATA.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(venv_python()),
            str(REPO_ROOT / "run_all.py"),
            "--db",
            str(DEFAULT_DB),
            "--export-json",
            str(DASHBOARD_DATA),
        ],
        cwd=REPO_ROOT,
    )


def main() -> None:
    args = set(sys.argv[1:])
    if "--force" in args:
        MARKER.unlink(missing_ok=True)
    if is_complete():
        if "--ensure" not in args:
            print("Setup already complete (use --force to redo).")
        return
    setup_python()
    export_dashboard_data()
    MARKER.write_text("ok\n", encoding="utf-8")
    print("Desktop setup complete.")


if __name__ == "__main__":
    main()
