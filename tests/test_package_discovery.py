"""Installed distributions must retain every SpiderWeb production module."""

import tomllib
from pathlib import Path

from setuptools import find_namespace_packages

ROOT = Path(__file__).resolve().parents[1]


def test_all_spiderweb_modules_are_in_distribution():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    included = config["tool"]["setuptools"]["packages"]["find"]["include"]
    packages = set(find_namespace_packages(where=str(ROOT), include=included))
    missing = {
        str(path.parent.relative_to(ROOT)).replace("/", ".")
        for path in (ROOT / "spiderweb").rglob("*.py")
    } - packages
    assert not missing, f"Production packages omitted from wheel: {sorted(missing)}"
    assert not any(name.startswith("spiderweb_pr_road_name") for name in packages)
