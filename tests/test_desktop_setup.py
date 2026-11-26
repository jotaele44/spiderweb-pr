"""Spiderweb's side of the shared launcher.

The launchers and desktop/setup.py are rendered from the federation hub
(thehub-pr/federation-templates), where their behaviour is tested and where
CI runs them on macOS, Windows and Linux. template-drift.yml keeps the copies
here identical to those templates. What is tested here is only what this
repository owns: its settings in desktop/config.py and its dependency pins.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from desktop import config, setup

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "PRII-SPIDERWEB.app" / "Contents"
RENDERED = [
    REPO_ROOT / "PRII-SPIDERWEB.command",
    REPO_ROOT / "PRII-SPIDERWEB.sh",
    REPO_ROOT / "PRII-SPIDERWEB.bat",
    APP / "MacOS" / "PRII-SPIDERWEB",
    APP / "Resources" / "first-run-setup.command",
    REPO_ROOT / "desktop" / "setup.py",
]


def test_min_python_matches_project_floor():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    floor = re.search(r">=\s*(\d+)\.(\d+)", project["requires-python"])
    assert config.MIN_PYTHON == (int(floor.group(1)), int(floor.group(2)))
    assert setup.MIN_PYTHON == config.MIN_PYTHON


def test_shared_setup_reads_this_apps_settings():
    assert setup.APP_TITLE == config.APP_TITLE
    assert setup.FRONTEND_DIR == config.FRONTEND_DIR
    assert setup.DIST_DIR == config.DIST_DIR
    assert setup.requirement_files() == [REPO_ROOT / "requirements-desktop.txt"]
    assert setup.CONSTRAINTS == REPO_ROOT / "constraints-desktop.txt"
    # The desktop build must stay same-origin and use GeoJSON delivery.
    assert config.EXTRA_BUILD_ENV["VITE_MUNICIPIOS_DELIVERY"] == "geojson"


@pytest.mark.parametrize("path", RENDERED, ids=lambda p: p.name)
def test_launcher_files_are_the_rendered_ones(path):
    text = path.read_text(encoding="utf-8")
    assert "thehub-pr/federation-templates/" in text
    if path.suffix in (".command", ".sh") or path.suffix == "":
        assert os.name == "nt" or os.access(path, os.X_OK)


def test_no_launcher_tells_the_person_to_run_a_command():
    for path in RENDERED[:5]:
        text = path.read_text(encoding="utf-8")
        assert "and run:" not in text
        assert "python3 desktop/setup.py" not in text


def test_setup_answers_without_installing_anything():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "desktop" / "setup.py"), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert config.APP_TITLE in result.stdout


def test_desktop_constraints_agree_with_the_lockfile():
    """A pin that drifts from uv.lock can make first-run `pip install` unsolvable.

    That happened: pydantic-core was pinned to a version the pinned pydantic
    rejects, so setup failed on every machine.
    """
    versions: dict[str, set[str]] = {}
    for package in tomllib.loads((REPO_ROOT / "uv.lock").read_text())["package"]:
        if "version" in package:
            name = package["name"].lower().replace("_", "-")
            versions.setdefault(name, set()).add(package["version"])
    drifted = []
    for line in setup.CONSTRAINTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        locked = versions.get(name.lower().replace("_", "-"))
        if locked and version not in locked:
            drifted.append(f"{line} (uv.lock: {', '.join(sorted(locked))})")
    assert not drifted, "constraints-desktop.txt disagrees with uv.lock:\n" + "\n".join(
        drifted
    )
