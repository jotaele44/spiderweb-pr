"""Paired, checkpoint-level rendered-ID conservation; never geometry identity.

MapLibre queryRenderedFeatures can repeat a feature across tile fragments.
Snapshots explicitly record unique IDs and their raw fragment count. The source
roster is independently duplicate-checked before these comparisons.
"""
from __future__ import annotations

import math
from typing import Any

from .core import set_receipt


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"INVALID_CAMERA_VALUE:{field}")
    if not math.isfinite(value):
        raise ValueError(f"NONFINITE_CAMERA_VALUE:{field}")
    return float(value)


def _ids(value: Any, field: str) -> set[str]:
    if not isinstance(value, list):
        raise ValueError(f"ID_LIST_REQUIRED:{field}")
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise ValueError(f"INVALID_RENDERED_ID:{field}")
    if len(value) != len(set(value)):
        raise ValueError(f"DUPLICATE_RENDERED_ID_SUMMARY:{field}")
    return set(value)


def _camera(snapshot: dict) -> dict:
    camera = snapshot.get("camera")
    if not isinstance(camera, dict) or not {"center", "canvas_pixels", "zoom", "pitch", "bearing"} <= set(camera):
        raise ValueError("CAMERA_RECEIPT_REQUIRED")
    for field in ("center", "canvas_pixels"):
        if not isinstance(camera.get(field), list) or len(camera[field]) != 2:
            raise ValueError(f"INVALID_CAMERA_FIELD:{field}")
    numbers = {key: _finite(camera[key], key) for key in ("zoom", "pitch", "bearing")}
    numbers["center"] = [_finite(n, "center") for n in camera["center"]]
    numbers["canvas_pixels"] = [_finite(n, "canvas_pixels") for n in camera["canvas_pixels"]]
    if not (-180 <= numbers["center"][0] <= 180 and -85 <= numbers["center"][1] <= 85):
        raise ValueError("CAMERA_OUT_OF_SCOPE")
    if any(n <= 0 or not n.is_integer() for n in numbers["canvas_pixels"]):
        raise ValueError("INVALID_CANVAS_PIXELS")
    return numbers


def _close(a: float, b: float) -> bool:
    # Explicit numeric camera equality tolerance, not a spatial identity rule.
    return math.isclose(a, b, rel_tol=0.0, abs_tol=1e-7)


def _matches_target(camera: dict, target: list, zoom: float, pixels: list) -> bool:
    return (
        all(_close(a, _finite(b, "target_center")) for a, b in zip(camera["center"], target))
        and _close(camera["zoom"], _finite(zoom, "target_zoom"))
        and _close(camera["pitch"], 0.0)
        and _close(camera["bearing"], 0.0)
        and camera["canvas_pixels"] == pixels
    )


def compare_rendered_trials(trials: list[dict], spec: dict, source_ids: set[str]) -> dict:
    """Compare both arms at initial view and every declared pan checkpoint.

    Missing/duplicate trials, invalid IDs and malformed camera observations
    raise. Real set differences are retained as FAIL, never discarded as noise.
    Optional expected_visible_ids supports independent synthetic/control-point
    expectations; absent expectations do not manufacture an analytical oracle.
    """
    if not source_ids or any(not isinstance(k, str) or not k.strip() for k in source_ids):
        raise ValueError("NONEMPTY_STRING_SOURCE_ROSTER_REQUIRED")
    views = spec.get("viewports")
    repetitions = spec.get("repetitions")
    if not isinstance(views, list) or not views:
        raise ValueError("NONEMPTY_VIEWPORT_DENOMINATOR_REQUIRED")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("POSITIVE_REPETITION_DENOMINATOR_REQUIRED")
    view_by_id = {}
    for view in views:
        vid = view.get("id")
        if not isinstance(vid, str) or not vid or vid in view_by_id:
            raise ValueError("INVALID_OR_DUPLICATE_VIEWPORT_ID")
        if type(view.get("expect_nonempty", True)) is not bool:
            raise ValueError("BOOLEAN_EXPECT_NONEMPTY_REQUIRED")
        view_by_id[vid] = view
    indexed = {}
    expected = {(vid, r, mode) for vid in view_by_id
                for r in range(repetitions) for mode in ("geojson", "mvt")}
    for row in trials:
        repetition = row.get("repetition")
        if type(repetition) is not int:
            raise ValueError("INTEGER_TRIAL_REPETITION_REQUIRED")
        key = (row.get("viewport_id"), repetition, row.get("mode"))
        if key not in expected:
            raise ValueError(f"UNEXPECTED_RENDERED_TRIAL:{key}")
        if key in indexed:
            raise ValueError(f"DUPLICATE_RENDERED_TRIAL:{key}")
        indexed[key] = row
    if set(indexed) != expected:
        raise ValueError(f"MISSING_RENDERED_TRIALS:{sorted(expected-set(indexed))}")
    viewport_pixels = spec.get("viewport_pixels", {"width": 1280, "height": 800})
    pixels = [viewport_pixels["width"], viewport_pixels["height"]]
    records = []
    for vid, view in view_by_id.items():
        targets = [("initial", view["center"])] + [
            (f"pan:{i}", target) for i, target in enumerate(view.get("pan_path", []))
        ]
        expected_steps = [step for step, _ in targets]
        oracle = view.get("expected_visible_ids", {})
        if not isinstance(oracle, dict) or set(oracle)-set(expected_steps):
            raise ValueError("INVALID_EXPECTED_VISIBLE_ID_STEPS")
        for repetition in range(repetitions):
            observed = {}
            for mode in ("geojson", "mvt"):
                measurement = indexed[(vid, repetition, mode)].get("measurement", {})
                snapshots = measurement.get("viewport_snapshots")
                if not isinstance(snapshots, list):
                    raise ValueError("VIEWPORT_SNAPSHOTS_REQUIRED")
                if [s.get("step_id") for s in snapshots] != expected_steps:
                    raise ValueError("MISSING_DUPLICATE_OR_REORDERED_CHECKPOINT")
                observed[mode] = dict(zip(expected_steps, snapshots))
            for step, target in targets:
                cameras = {}; ids = {}; fragments = {}; errors = []
                for mode in ("geojson", "mvt"):
                    snap = observed[mode][step]
                    cameras[mode] = _camera(snap)
                    ids[mode] = _ids(snap.get("visible_ids"), f"{vid}:{step}:{mode}")
                    count = snap.get("rendered_fragment_count")
                    if type(count) is not int or count < len(ids[mode]) or (not ids[mode] and count != 0):
                        raise ValueError("INVALID_RENDERED_FRAGMENT_COUNT")
                    fragments[mode] = count
                    if ids[mode]-source_ids:
                        errors.append(f"{mode}:UNKNOWN_SOURCE_IDS")
                    if view.get("expect_nonempty", True) and not ids[mode]:
                        errors.append(f"{mode}:UNEXPECTED_EMPTY_VIEW")
                    if not _matches_target(cameras[mode], target, view["zoom"], pixels):
                        errors.append(f"{mode}:CAMERA_TARGET_MISMATCH")
                diff = set_receipt(ids["geojson"], ids["mvt"])
                if diff["counts"]["symmetric_difference"]:
                    errors.append("RENDERED_ID_SET_MISMATCH")
                expected_ids = _ids(oracle[step], "expected_visible_ids") if step in oracle else None
                oracle_diffs = None
                if expected_ids is not None:
                    if expected_ids-source_ids:
                        raise ValueError("ORACLE_CONTAINS_UNKNOWN_SOURCE_ID")
                    oracle_diffs = {m: set_receipt(expected_ids, ids[m]) for m in ids}
                    if any(d["counts"]["symmetric_difference"] for d in oracle_diffs.values()):
                        errors.append("INDEPENDENT_VISIBLE_ID_EXPECTATION_FAILED")
                records.append({
                    "viewport_id": vid, "repetition": repetition, "step_id": step,
                    "state": "PASS" if not errors else "FAIL", "errors": errors,
                    "sets": diff, "cameras": cameras, "rendered_fragments": fragments,
                    "unknown_ids": {m: sorted(ids[m]-source_ids) for m in ids},
                    "independent_expectation": oracle_diffs,
                })
    failed = sum(r["state"] != "PASS" for r in records)
    return {
        "state": "PASS_RENDERED_ID_PARITY" if not failed else "FAIL_RENDERED_ID_PARITY",
        "scope": "declared paired viewport/checkpoint rendered-ID sets only",
        "geometry_equality_proven": False, "canonical_identity_certified": False,
        "trial_count": len(trials), "paired_checkpoint_count": len(records),
        "failed_checkpoint_count": failed, "records": records,
    }
