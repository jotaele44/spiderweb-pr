"""Boundary gate: Spiderweb no longer contains active FR24 screenshot-processing
implementations. Asserts the removed modules are gone, the removed CLI flags are
absent, and the named FR24 symbols do not appear in active source.

Matches of the removed symbols are permitted only in removal/migration docs and
in this boundary test itself.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REMOVED_MODULES = [
    "pipeline.flight_analyzer",
    "pipeline.hardened_pipeline",
    "pipeline.home_base_correlation",
    "pipeline.ensemble_ocr",
]

REMOVED_SYMBOLS = [
    "FlightAnalyzer",
    "FlightRadarOCR",
    "process_all_images",
    "process_with_hardening",
    "link_screenshots_to_flights",
    "/mnt/user-data/uploads",
]


@pytest.mark.parametrize("modname", REMOVED_MODULES)
def test_removed_modules_not_importable(modname):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(modname)


def test_run_all_has_no_screenshot_flags():
    # run_all builds its parser inside main(); assert the source has no FR24 flags.
    src = (_REPO_ROOT / "run_all.py").read_text(encoding="utf-8")
    assert "--image-dir" not in src
    assert "--images" not in src
    assert "run_phase_0" not in src
    assert "run_phase_1" not in src
    assert "--ingest-skywatcher" not in src


def _iter_active_py():
    skip_dirs = {".git", "tests", "docs", "node_modules", "__pycache__"}
    for path in _REPO_ROOT.rglob("*.py"):
        parts = set(path.relative_to(_REPO_ROOT).parts)
        if parts & skip_dirs:
            continue
        yield path


@pytest.mark.parametrize("symbol", REMOVED_SYMBOLS)
def test_no_active_fr24_symbols_in_source(symbol):
    offenders = []
    for path in _iter_active_py():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if symbol in text:
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, f"{symbol!r} still present in active source: {offenders}"
