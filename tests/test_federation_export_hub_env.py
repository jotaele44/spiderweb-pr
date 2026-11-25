"""The hub runs this repository's federation export with only the hub's packages.

thehub-pr's ``federation-ingest.yml`` installs the hub and ``prii-export-utils``,
clones this repository, and runs ``hub_callable_commands.export_canonical`` from
``federation.json``. None of this repository's own dependencies (numpy, scipy,
shapely, xarray, ...) are installed there. Spiderweb commit 1746045 added the
access-point lane to that command; its import chain reached numpy through
``gebco/__init__`` and shapely through ``spiderweb/subsurface/__init__``, and every
hub ingest failed until both packages loaded those modules lazily.

These tests run the export in a subprocess that refuses to import every base
dependency in ``pyproject.toml`` the hub does not install.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
pytest.importorskip("prii_export_utils")

# What thehub-pr's federation-ingest job installs besides the standard library
# (`pip install -e ".[dev]" -e packages/prii_export_utils`): the hub's runtime
# dependencies and prii-export-utils.
HUB_PROVIDED = {"prii-export-utils", "pyyaml", "jsonschema"}
NOW = "2026-11-21T00:00:00Z"


def _dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _blocked_modules() -> list[str]:
    """Top-level modules of the base dependencies the hub does not install."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    deps = tomllib.loads(pyproject)["project"]["dependencies"]
    wanted = {_dist(re.split(r"[\s<>=!~;\[@]", dep, maxsplit=1)[0]) for dep in deps}
    missing_in_hub = wanted - HUB_PROVIDED
    blocked = {
        module
        for module, dists in importlib.metadata.packages_distributions().items()
        if dists and all(_dist(d) in missing_in_hub for d in dists)
    }
    # Guard against the mapping silently coming back empty.
    assert {"numpy", "shapely"} <= blocked, sorted(blocked)
    return sorted(blocked)


_BLOCKER = """
import sys
BLOCKED = frozenset({blocked!r})

class _NotInHubIngest:
    def find_spec(self, name, path=None, target=None):
        if name.partition(".")[0] in BLOCKED:
            raise ModuleNotFoundError(
                f"No module named {{name!r}} (not installed by the hub ingest)",
                name=name,
            )
        return None

sys.meta_path.insert(0, _NotInHubIngest())
"""


def _run(code: str, *args: str, block: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter, by default without the blocked modules."""
    prelude = _BLOCKER.format(blocked=_blocked_modules()) if block else "import sys\n"
    script = prelude + code
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_the_hub_export_command_runs_without_this_repos_dependencies(tmp_path):
    manifest = json.loads((REPO / "federation.json").read_text(encoding="utf-8"))
    argv = shlex.split(manifest["hub_callable_commands"]["export_canonical"])
    assert argv[:2] == ["python3", "scripts/federation_export.py"], argv
    out = tmp_path / "federation"
    run_script = (
        "import runpy\n"
        "sys.argv = sys.argv[1:]\n"
        "sys.path.insert(0, 'scripts')\n"
        "runpy.run_path('scripts/federation_export.py', run_name='__main__')\n"
    )
    proc = _run(run_script, *argv[1:], "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-4000:]
    written = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert written["producer"] == "spiderweb-pr"
    if "--access-point-registries" in argv:
        assert "access points:" in proc.stdout + proc.stderr


def test_the_access_point_lane_is_identical_without_this_repos_dependencies():
    lane_script = (
        "import importlib.util, json\n"
        "from pathlib import Path\n"
        "sys.path[:0] = ['scripts', '.']\n"
        "spec = importlib.util.spec_from_file_location(\n"
        "    'fx', 'scripts/federation_export.py'\n"
        ")\n"
        "fx = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(fx)\n"
        f"lane = fx.build_access_point_lane(Path('registry/access_points'), {NOW!r})\n"
        "print(json.dumps(lane, sort_keys=True))\n"
    )
    # The same script with and without the blocker, so the only difference between
    # the two runs is which modules can be imported.
    without = _run(lane_script)
    assert without.returncode == 0, without.stderr[-4000:]
    full = _run(lane_script, block=False)
    assert full.returncode == 0, full.stderr[-4000:]
    lane = json.loads(without.stdout)
    assert lane == json.loads(full.stdout)
    assert lane["entities"], "the committed registries export at least one record"
