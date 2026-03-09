"""
EarthGPT iOS — Terrain path filter.

Penalizes corridor candidates that cross implausible terrain
(e.g., mostly water with no structural context).
"""

from typing import List


def apply_terrain_filter(candidates: List[dict], water_penalty: float = 0.5) -> List[dict]:
    """
    Reduce rank_score for candidates that are predominantly over water.

    Expects candidates to have an optional ``dominant_tile_type`` field.
    """
    for c in candidates:
        tile_type = c.get("dominant_tile_type", "land")
        if tile_type == "water":
            c["rank_score"] = round(float(c.get("rank_score", 0.0)) * water_penalty, 4)
            c["terrain_filtered"] = True
    return candidates
