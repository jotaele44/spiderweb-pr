"""Catalog / acquisition-cadence helpers.

Two corrections from the architecture brief live here:

* Correction #1 — **do not hard-code a Sentinel-1 12-day cadence.** The observed
  revisit interval is computed from the acquisition timestamps of the *actual*
  compatible scenes returned by a catalog search. There is deliberately no
  ``EXPECTED_REVISIT_DAYS = 12`` constant anywhere in this module.
* An InSAR pair is only valid when the two acquisitions match on relative orbit,
  acquisition mode, polarization, overlapping footprint, processing
  compatibility, and a usable baseline. ``insar_pair_compatibility`` returns the
  explicit reasons a pair is rejected rather than a bare bool, so exclusions are
  auditable.

Everything here is stdlib-only and works on lightweight scene dicts (or the
``SceneMetadata``-shaped dicts produced by ``imagery/``), so no network or
geospatial dependency is required.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Optional, Sequence


def _parse_ts(value: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 parse; returns None on anything unparseable."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Fall back to date-only.
        try:
            dt = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    # Normalize to naive UTC for interval math.
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    return dt


def _acquired_at(scene: Dict[str, Any]) -> Any:
    """Pull an acquisition timestamp from a scene dict, tolerant of shapes."""
    for key in ("acquired_at", "acquisition_start", "datetime", "acquisition_end"):
        if scene.get(key):
            return scene[key]
    return None


def observed_revisit_days(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the *observed* revisit cadence from real acquisition times.

    Returns a summary dict::

        {
            "scene_count": int,
            "intervals_days": [float, ...],   # consecutive gaps, sorted by time
            "min_days": float | None,
            "median_days": float | None,
            "max_days": float | None,
        }

    A single scene (or none) yields empty intervals and None statistics — the
    correct answer when the catalog cannot establish a cadence, rather than a
    fabricated default.
    """
    times = sorted(
        t for t in (_parse_ts(_acquired_at(s)) for s in scenes) if t is not None
    )
    intervals: List[float] = []
    for earlier, later in zip(times, times[1:]):
        intervals.append(round((later - earlier).total_seconds() / 86400.0, 4))

    if not intervals:
        return {
            "scene_count": len(times),
            "intervals_days": [],
            "min_days": None,
            "median_days": None,
            "max_days": None,
        }
    return {
        "scene_count": len(times),
        "intervals_days": intervals,
        "min_days": min(intervals),
        "median_days": round(median(intervals), 4),
        "max_days": max(intervals),
    }


def _footprints_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Cheap bbox-overlap test using each scene's ``bbox`` (w, s, e, n)."""
    ba, bb = a.get("bbox"), b.get("bbox")
    if not ba or not bb or len(ba) < 4 or len(bb) < 4:
        # Cannot prove non-overlap → do not reject on this ground alone.
        return True
    aw, as_, ae, an = ba[:4]
    bw, bs, be, bn = bb[:4]
    return not (ae < bw or be < aw or an < bs or bn < as_)


def insar_pair_compatibility(
    reference: Dict[str, Any],
    secondary: Dict[str, Any],
    *,
    max_perp_baseline_m: float = 300.0,
    min_temporal_baseline_days: float = 0.5,
) -> Dict[str, Any]:
    """Test whether two SLC scenes may form a valid interferometric pair.

    Checks relative orbit, acquisition mode, polarization, footprint overlap,
    processing compatibility, and usable perpendicular / temporal baselines.
    Returns ``{"compatible": bool, "reasons": [...], "temporal_baseline_days": ...}``
    where ``reasons`` lists every failed gate (empty when compatible).
    """
    reasons: List[str] = []

    def _get(scene: Dict[str, Any], *keys: str) -> Any:
        for k in keys:
            if scene.get(k) is not None:
                return scene[k]
        return None

    ref_orbit = _get(reference, "relative_orbit")
    sec_orbit = _get(secondary, "relative_orbit")
    if ref_orbit is None or sec_orbit is None:
        reasons.append("relative_orbit missing on one or both scenes")
    elif ref_orbit != sec_orbit:
        reasons.append(f"relative_orbit mismatch ({ref_orbit} != {sec_orbit})")

    if _get(reference, "acquisition_mode", "sensor_mode") != _get(
        secondary, "acquisition_mode", "sensor_mode"
    ):
        reasons.append("acquisition_mode mismatch")

    if _get(reference, "polarization") != _get(secondary, "polarization"):
        reasons.append("polarization mismatch")

    if not _footprints_overlap(reference, secondary):
        reasons.append("footprints do not overlap")

    if _get(reference, "processing_baseline") != _get(secondary, "processing_baseline"):
        reasons.append("processing_baseline mismatch")

    perp = secondary.get("perpendicular_baseline_m")
    if perp is not None and abs(float(perp)) > max_perp_baseline_m:
        reasons.append(f"perpendicular baseline {perp}m exceeds {max_perp_baseline_m}m")

    t_ref = _parse_ts(_acquired_at(reference))
    t_sec = _parse_ts(_acquired_at(secondary))
    temporal_days: Optional[float] = None
    if t_ref is None or t_sec is None:
        reasons.append("acquisition time missing on one or both scenes")
    else:
        temporal_days = round(abs((t_sec - t_ref).total_seconds()) / 86400.0, 4)
        if temporal_days < min_temporal_baseline_days:
            reasons.append(
                f"temporal baseline {temporal_days}d below "
                f"{min_temporal_baseline_days}d minimum"
            )

    return {
        "compatible": not reasons,
        "reasons": reasons,
        "temporal_baseline_days": temporal_days,
    }


def compatible_pairs(
    scenes: Sequence[Dict[str, Any]], **kwargs
) -> List[Dict[str, Any]]:
    """Enumerate valid InSAR pairs among ``scenes`` (chronological reference).

    Returns one entry per compatible ordered pair::

        {"reference": scene, "secondary": scene, "temporal_baseline_days": float}
    """
    ordered = sorted(scenes, key=lambda s: (_parse_ts(_acquired_at(s)) or datetime.min))
    out: List[Dict[str, Any]] = []
    for i, ref in enumerate(ordered):
        for sec in ordered[i + 1 :]:
            result = insar_pair_compatibility(ref, sec, **kwargs)
            if result["compatible"]:
                out.append(
                    {
                        "reference": ref,
                        "secondary": sec,
                        "temporal_baseline_days": result["temporal_baseline_days"],
                    }
                )
    return out
