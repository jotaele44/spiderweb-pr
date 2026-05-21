"""
EarthGPT iOS — Context-normalised scoring.

Adjusts raw anomaly scores based on tile context (coast, water, land)
to reduce false positives near water or coast boundaries.
"""

from typing import Any, Dict


def normalize_score(
    raw_score: float,
    tile_type: str = "land",
    coast_weight: float = 1.0,
    water_weight: float = 1.0,
) -> float:
    """
    Apply context penalties to a raw anomaly score.

    Water tiles get reduced sensitivity (shorelines look anomalous by default).
    Coast tiles get a moderate penalty.

    Returns a float in [0, 1].
    """
    score = float(raw_score)
    if tile_type == "water":
        score *= water_weight * 0.6
    elif tile_type == "coast":
        score *= coast_weight * 0.8
    return max(0.0, min(1.0, score))


def normalize_seam_score(
    raw_score: float,
    edge_of_grid: bool = False,
    tile_type: str = "land",
) -> float:
    """
    Apply seam-specific normalizations.

    Edge-of-grid tiles are penalized because seams there may be artefacts.
    """
    score = normalize_score(raw_score, tile_type=tile_type)
    if edge_of_grid:
        score *= 0.5
    return score


_REQUIRED_TILE_FIELDS = ("x", "y", "zoom", "tile_type")
_VALID_TILE_TYPES = ("land", "water", "coast")


def validate(context: Dict) -> None:
    """Check all required tile context fields before pipeline entry.

    Accepts a dict with keys: x, y, zoom, tile_type.

    Raises
    ------
    ValueError
        If required fields are missing or tile_type is not in the allowed set.
    """
    missing = [f for f in _REQUIRED_TILE_FIELDS if f not in context]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    tile_type = context.get("tile_type")
    if tile_type not in _VALID_TILE_TYPES:
        raise ValueError(
            f"tile_type must be one of {_VALID_TILE_TYPES}, got {tile_type!r}"
        )
