"""Tests for run_modes — strict/demo/normal mode resolution and gating."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from run_modes import (  # noqa: E402
    MODE_DEMO,
    MODE_NORMAL,
    MODE_STRICT,
    assert_production_input,
    label_banner,
    label_manifest,
    resolve_mode,
)


def _args(**kwargs):
    """Build an argparse.Namespace with the run_modes-relevant flags."""
    ns = argparse.Namespace()
    ns.strict_production = kwargs.get("strict_production", False)
    ns.demo = kwargs.get("demo", False)
    return ns


# ── resolve_mode ────────────────────────────────────────────────────────────


def test_resolve_mode_default_is_normal():
    m = resolve_mode(_args())
    assert m.mode == MODE_NORMAL
    assert m.fail_on_missing is False
    assert m.label_outputs is False


def test_resolve_mode_demo():
    m = resolve_mode(_args(demo=True))
    assert m.mode == MODE_DEMO
    assert m.fail_on_missing is False
    assert m.label_outputs is True


def test_resolve_mode_strict():
    m = resolve_mode(_args(strict_production=True))
    assert m.mode == MODE_STRICT
    assert m.fail_on_missing is True
    assert m.label_outputs is False


def test_resolve_mode_both_strict_wins(capsys):
    """Strict and demo together — strict wins, warning to stderr."""
    m = resolve_mode(_args(strict_production=True, demo=True))
    assert m.mode == MODE_STRICT
    captured = capsys.readouterr()
    assert "both passed" in captured.err.lower() or "strict" in captured.err.lower()


# ── assert_production_input ─────────────────────────────────────────────────


def test_assert_production_input_normal_returns_silently(tmp_path):
    """Normal mode never raises — soft contract."""
    m = resolve_mode(_args())
    assert_production_input(str(tmp_path / "nope.db"),
                            stage="test", hint="run pipeline", mode=m)


def test_assert_production_input_strict_missing_exits_2(capsys):
    m = resolve_mode(_args(strict_production=True))
    with pytest.raises(SystemExit) as ei:
        assert_production_input("/nonexistent/path/db.sqlite",
                                stage="release_check",
                                hint="run pipeline to populate", mode=m)
    assert ei.value.code == 2
    err = capsys.readouterr().err
    payload = json.loads(err.splitlines()[-1])
    assert payload["error"] == "strict_production_input_missing"
    assert payload["stage"] == "release_check"
    assert payload["reason"] == "missing"
    assert payload["hint"] == "run pipeline to populate"


def test_assert_production_input_strict_empty_file_exits_2(tmp_path):
    """Strict mode flags empty files as missing too."""
    p = tmp_path / "empty.db"
    p.write_bytes(b"")
    m = resolve_mode(_args(strict_production=True))
    with pytest.raises(SystemExit) as ei:
        assert_production_input(str(p), stage="x", hint="y", mode=m,
                                require_nonempty=True)
    assert ei.value.code == 2


def test_assert_production_input_strict_nonempty_file_passes(tmp_path):
    p = tmp_path / "ok.db"
    p.write_bytes(b"x")
    m = resolve_mode(_args(strict_production=True))
    # Should not raise
    assert_production_input(str(p), stage="x", hint="y", mode=m,
                            require_nonempty=True)


# ── labels ──────────────────────────────────────────────────────────────────


def test_label_banner_demo_prefixes():
    m = resolve_mode(_args(demo=True))
    assert label_banner("PHASE 1", m) == "[DEMO] PHASE 1"


def test_label_banner_normal_unchanged():
    m = resolve_mode(_args())
    assert label_banner("PHASE 1", m) == "PHASE 1"


def test_label_manifest_demo_stamps_mode_and_warning():
    m = resolve_mode(_args(demo=True))
    manifest = {}
    out = label_manifest(manifest, m)
    assert out is manifest  # mutates in-place
    assert manifest["mode"] == "demo"
    assert "demo_warning" in manifest


def test_label_manifest_normal_only_stamps_mode():
    m = resolve_mode(_args())
    manifest = {}
    label_manifest(manifest, m)
    assert manifest["mode"] == "normal"
    assert "demo_warning" not in manifest
