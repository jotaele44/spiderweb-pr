"""
RUN MODES
Resolves --strict-production / --demo / (default) normal modes for run_all.py
exports.  Each ``_run_*`` helper in run_all.py consults ``resolve_mode(args)``
and passes the result to its underlying adapter so the mode propagates into
the manifest reproducibility block (see provenance_utils.reproducibility_metadata).

Contract:
  strict — missing or empty production inputs raise SystemExit(2) with a
           structured one-line JSON error to stderr.
  demo   — outputs include ``"mode": "demo"`` and stage banners are prefixed
           with ``[DEMO]``.
  normal — current behavior; no labeling, soft on missing inputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


MODE_NORMAL = "normal"
MODE_DEMO = "demo"
MODE_STRICT = "strict"
ALLOWED_MODES = (MODE_NORMAL, MODE_DEMO, MODE_STRICT)


class ModeResolution:
    """Resolved mode + downstream behavior flags."""

    __slots__ = ("mode", "fail_on_missing", "label_outputs")

    def __init__(self, mode: str, fail_on_missing: bool, label_outputs: bool):
        self.mode = mode
        self.fail_on_missing = fail_on_missing
        self.label_outputs = label_outputs

    def __repr__(self) -> str:
        return (
            f"ModeResolution(mode={self.mode!r}, "
            f"fail_on_missing={self.fail_on_missing}, "
            f"label_outputs={self.label_outputs})"
        )

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "fail_on_missing": self.fail_on_missing,
            "label_outputs": self.label_outputs,
        }


def resolve_mode(args) -> ModeResolution:
    """Convert argparse Namespace flags into a ModeResolution.

    Strict and demo are mutually exclusive.  When both are passed, strict wins
    and a warning is printed to stderr so the operator notices.
    """
    strict = bool(getattr(args, "strict_production", False))
    demo = bool(getattr(args, "demo", False))

    if strict and demo:
        print(
            "  Warning: --strict-production and --demo both passed; using strict.",
            file=sys.stderr,
        )
        demo = False

    if strict:
        return ModeResolution(MODE_STRICT, fail_on_missing=True, label_outputs=False)
    if demo:
        return ModeResolution(MODE_DEMO, fail_on_missing=False, label_outputs=True)
    return ModeResolution(MODE_NORMAL, fail_on_missing=False, label_outputs=False)


def assert_production_input(
    path: Optional[str],
    *,
    stage: str,
    hint: str,
    mode: ModeResolution,
    require_nonempty: bool = True,
) -> None:
    """Validate that *path* exists (and optionally is non-empty) for production.

    In strict mode: missing / empty / unreadable → SystemExit(2) with structured
    error.  In demo / normal mode: silently returns (mode propagation is the
    caller's responsibility).
    """
    if mode.mode != MODE_STRICT:
        return
    p = Path(path) if path else None
    missing = False
    reason = ""
    if not p or not p.exists():
        missing = True
        reason = "missing"
    elif require_nonempty:
        try:
            if p.is_file() and p.stat().st_size == 0:
                missing = True
                reason = "empty_file"
        except OSError:
            missing = True
            reason = "unreadable"
    if missing:
        err = {
            "error": "strict_production_input_missing",
            "stage": stage,
            "path": str(path),
            "reason": reason,
            "hint": hint,
        }
        print(json.dumps(err), file=sys.stderr)
        raise SystemExit(2)


def label_banner(text: str, mode: ModeResolution) -> str:
    """Decorate a stage banner with ``[DEMO]`` prefix when in demo mode."""
    if mode.label_outputs:
        return f"[DEMO] {text}"
    return text


def label_manifest(manifest: dict, mode: ModeResolution) -> dict:
    """Stamp the manifest with the resolved mode for downstream consumers."""
    manifest["mode"] = mode.mode
    if mode.mode == MODE_DEMO:
        manifest["demo_warning"] = (
            "This manifest was produced in --demo mode. Do not treat outputs "
            "as production data."
        )
    return manifest
