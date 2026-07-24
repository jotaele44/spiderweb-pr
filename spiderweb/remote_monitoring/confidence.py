"""Confidence scoring for remote observations.

Implements the brief's seven-component additive model. Each component is scored
0..1 and scaled by its maximum contribution (``schemas.CONFIDENCE_COMPONENTS``,
which sums to 100). The resulting 0..100 score maps to a classification band
(``schemas.CONFIDENCE_BANDS``).

The band names the *strength of the surface-change signal only*. It is
intentionally NOT an event classification: an 88/100 "high_confidence_change"
says the change is real and well-corroborated, not that it is confirmed dredging,
a landslide, or earthwork — that determination is a separate adjudication.
"""

from __future__ import annotations

from typing import Dict, Mapping

from . import schemas


def score_confidence(components: Mapping[str, float]) -> float:
    """Combine per-component 0..1 scores into a 0..100 total.

    Unknown component keys are ignored; missing components contribute 0. Each
    input is clamped to [0, 1] before scaling so a mis-scaled input cannot push
    the total past 100.
    """
    total = 0.0
    for name, weight in schemas.CONFIDENCE_COMPONENTS.items():
        raw = float(components.get(name, 0.0))
        clamped = 0.0 if raw < 0.0 else 1.0 if raw > 1.0 else raw
        total += clamped * weight
    return round(total, 2)


def classify(score: float) -> str:
    """Map a 0..100 confidence score to its band label."""
    for threshold, label in schemas.CONFIDENCE_BANDS:
        if score >= threshold:
            return label
    # CONFIDENCE_BANDS ends at 0, so this is unreachable for score >= 0.
    return schemas.CONFIDENCE_BANDS[-1][1]


def assess(components: Mapping[str, float]) -> Dict[str, object]:
    """Return ``{"score", "band", "components"}`` for a component mapping."""
    score = score_confidence(components)
    return {
        "score": score,
        "band": classify(score),
        "components": {
            k: float(components.get(k, 0.0)) for k in schemas.CONFIDENCE_COMPONENTS
        },
    }
