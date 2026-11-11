"""Temporal change score: a port of skywatcher-pr's ``score_temporal_change``.

Re-implemented from the SATIM spec, not imported (this repository forbids cross-repo
imports), and cross-checked numerically against the original in the tests.

**Every threshold and weight below is an uncalibrated heuristic.** They are copied
from the SATIM spec so the two engines agree; nothing here claims a detection
accuracy. The output is a visible-change signal between two dated epochs and never a
cause, an owner or a purpose (``NO_CAUSAL_INFERENCE``).
"""

from __future__ import annotations

from typing import Any

from .models import ChangeType, TemporalClass, TemporalObservation, TemporalScore

# Copied from the SATIM spec (uncalibrated).
ALIGNMENT_FLOOR = 0.6
ARTIFACT_HIGH = 0.7
ARTIFACT_CHANGE_FLOOR = 0.35
CONFIRMED_FLOOR = 0.7
PROBABLE_FLOOR = 0.35
ARTIFACT_WEIGHT = 0.6
CONTRADICTION_WEIGHT = 0.3
CONTRADICTION_HIGH = 0.7

# Chosen here (uncalibrated). Imagery coarser than this cannot support a claim about
# an individual feature, so only coarse change classes are allowed.
COARSE_ONLY_ABOVE_M = 5.0
COARSE_CHANGE_TYPES = frozenset(
    {
        ChangeType.EXPANSION.value,
        ChangeType.CONTRACTION.value,
        ChangeType.SURFACE_COVER_CHANGE.value,
    }
)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def restrict_to_resolution(
    signals: dict[str, float], resolution_m: float | None
) -> tuple[dict[str, float], tuple[str, ...]]:
    """Drop change classes the imagery resolution cannot support.

    A missing resolution is treated as coarse. Returns ``(kept, dropped)``.
    """
    coarse = resolution_m is None or resolution_m > COARSE_ONLY_ABOVE_M
    if not coarse:
        return dict(signals), ()
    kept = {k: v for k, v in signals.items() if k in COARSE_CHANGE_TYPES}
    dropped = tuple(sorted(k for k in signals if k not in COARSE_CHANGE_TYPES))
    return kept, dropped


def _normalized_changes(observation: TemporalObservation) -> dict[str, float]:
    allowed = {item.value for item in ChangeType}
    return {
        str(key): clamp01(value)
        for key, value in observation.change_signals.items()
        if str(key) in allowed
    }


def score_temporal_change(observation: TemporalObservation) -> TemporalScore:
    changes = _normalized_changes(observation)
    change_score = round(max(changes.values(), default=0.0), 4)
    alignment = round(
        (
            clamp01(observation.spatial_overlap)
            + clamp01(observation.registration_quality)
            + clamp01(observation.scale_compatibility)
            + clamp01(observation.view_angle_compatibility)
        )
        / 4.0,
        4,
    )
    artifact = round(clamp01(observation.artifact_confidence), 4)
    contradiction = round(clamp01(observation.contradiction_confidence), 4)
    adjusted = round(
        clamp01(
            change_score
            * alignment
            * (1.0 - ARTIFACT_WEIGHT * artifact)
            * (1.0 - CONTRADICTION_WEIGHT * contradiction)
        ),
        4,
    )

    if alignment < ALIGNMENT_FLOOR:
        classification = TemporalClass.INSUFFICIENT_EPOCH_ALIGNMENT
    elif artifact >= ARTIFACT_HIGH and change_score >= ARTIFACT_CHANGE_FLOOR:
        classification = TemporalClass.ARTIFACT_DRIVEN_CHANGE
    elif adjusted >= CONFIRMED_FLOOR:
        classification = TemporalClass.CONFIRMED_VISIBLE_CHANGE
    elif adjusted >= PROBABLE_FLOOR:
        classification = TemporalClass.PROBABLE_CHANGE
    else:
        classification = TemporalClass.STABLE

    reasons: list[str] = []
    if alignment < ALIGNMENT_FLOOR:
        reasons.append("LOW_EPOCH_ALIGNMENT")
    if artifact >= ARTIFACT_HIGH:
        reasons.append("HIGH_ARTIFACT_CONFIDENCE")
    if contradiction >= CONTRADICTION_HIGH:
        reasons.append("HIGH_CONTRADICTION_CONFIDENCE")
    if not observation.before.provenance:
        reasons.append("MISSING_BEFORE_PROVENANCE")
    if not observation.after.provenance:
        reasons.append("MISSING_AFTER_PROVENANCE")

    return TemporalScore(
        comparison_id=observation.comparison_id,
        classification=classification.value,
        change_score=change_score,
        alignment_score=alignment,
        artifact_confidence=artifact,
        contradiction_confidence=contradiction,
        adjusted_change_score=adjusted,
        change_types=tuple(sorted(n for n, v in changes.items() if v > 0.0)),
        review_required=classification
        in {
            TemporalClass.ARTIFACT_DRIVEN_CHANGE,
            TemporalClass.INSUFFICIENT_EPOCH_ALIGNMENT,
        }
        or bool(reasons),
        review_reasons=tuple(sorted(set(reasons))),
    )


def score_summary(score: TemporalScore) -> dict[str, Any]:
    """JSON-safe view of a score."""
    return {
        "classification": score.classification,
        "change_score": score.change_score,
        "alignment_score": score.alignment_score,
        "artifact_confidence": score.artifact_confidence,
        "contradiction_confidence": score.contradiction_confidence,
        "adjusted_change_score": score.adjusted_change_score,
        "change_types": list(score.change_types),
        "review_required": score.review_required,
        "review_reasons": list(score.review_reasons),
    }
