"""
EarthGPT iOS — Propagation logic.

Propagates anomaly scores to neighbouring tiles using lightweight
anisotropic weighting. Returns empty output gracefully if no anomalies.
"""

import math
from typing import Dict, List, Optional, Tuple

from .tile_utils import tile_neighbors


def _orientation_angle(scores: Dict[Tuple[int, int], float]) -> Tuple[float, float]:
    """
    Estimate dominant orientation angle and directional confidence
    from a spatial score map.

    Returns (angle_deg, confidence) where confidence is 0-1.
    """
    if not scores:
        return 0.0, 0.0

    # Compute weighted center of mass
    total_weight = sum(scores.values())
    if total_weight == 0:
        return 0.0, 0.0

    cx = sum(x * s for (x, y), s in scores.items()) / total_weight
    cy = sum(y * s for (x, y), s in scores.items()) / total_weight

    # Principal axis via inertia
    Ixx = Ixy = Iyy = 0.0
    for (x, y), s in scores.items():
        dx, dy = x - cx, y - cy
        Ixx += s * dx * dx
        Ixy += s * dx * dy
        Iyy += s * dy * dy

    # Angle of principal axis
    if abs(Ixx - Iyy) < 1e-9 and abs(Ixy) < 1e-9:
        angle = 0.0
        confidence = 0.0
    else:
        angle = 0.5 * math.degrees(math.atan2(2 * Ixy, Ixx - Iyy))
        spread = math.sqrt((Ixx - Iyy) ** 2 + 4 * Ixy ** 2)
        confidence = min(spread / (Ixx + Iyy + 1e-9), 1.0)

    return round(angle, 2), round(confidence, 4)


def propagate_scores(
    nodes: List[dict],
    zoom: int = 15,
    n_neighbors: int = 8,
    score_field: str = "score",
    anisotropic: bool = True,
) -> List[dict]:
    """
    Propagate anomaly scores to neighbours.

    For each anomaly node, neighbouring tiles receive a fraction of
    the source score. If anisotropic=True, scores are weighted by
    alignment with the dominant orientation.

    Returns a list of propagated node dicts.
    """
    score_map: Dict[Tuple[int, int], float] = {}
    orig_map: Dict[Tuple[int, int], dict] = {}

    for n in nodes:
        x, y = int(n.get("x", 0)), int(n.get("y", 0))
        score_map[(x, y)] = float(n.get(score_field, 0.0))
        orig_map[(x, y)] = n

    if not score_map:
        return []

    angle, confidence = _orientation_angle(score_map)
    angle_rad = math.radians(angle)

    propagated: Dict[Tuple[int, int], dict] = {}

    for (x, y), score in score_map.items():
        for nx, ny in tile_neighbors(x, y, zoom, n=n_neighbors):
            if score < 0.1:
                continue
            dx, dy = nx - x, ny - y
            nb_angle = math.atan2(dy, dx)
            if anisotropic and confidence > 0.1:
                alignment = abs(math.cos(nb_angle - angle_rad))
                gain = 0.5 + 0.5 * alignment
            else:
                gain = 1.0

            prop_score = score * 0.4 * gain

            if (nx, ny) not in propagated:
                propagated[(nx, ny)] = {
                    "x": nx,
                    "y": ny,
                    "zoom": zoom,
                    "score": 0.0,
                    "decision": "normal",
                    "risk_final_v2_0_100": 0.0,
                    "status": "propagated",
                    "orientation_angle": angle,
                    "directional_confidence": confidence,
                    "anisotropic_gain": round(gain, 4),
                }

            existing = propagated[(nx, ny)]["score"]
            propagated[(nx, ny)]["score"] = round(max(existing, prop_score), 4)
            propagated[(nx, ny)]["risk_final_v2_0_100"] = round(
                propagated[(nx, ny)]["score"] * 100.0, 2
            )

    # Merge originals with propagated (originals take priority)
    result = list(orig_map.values())
    for key, p in propagated.items():
        if key not in orig_map:
            result.append(p)

    return result
