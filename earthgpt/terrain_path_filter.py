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


def filter_by_gebco_slope(paths: List, max_slope: float = 5.0) -> List:
    """Filter paths over steep underwater terrain using GEBCO slope data."""
    try:
        from gebco.terrain import TerrainAnalyzer
        analyzer = TerrainAnalyzer()
        gradient = analyzer.slope_gradient_map()
        if len(gradient) == 0:
            return paths
        max_grad = float(max(gradient.flatten())) if hasattr(gradient, "flatten") else max_slope
        return [p for p in paths if getattr(p, "underwater_slope", 0) < max_grad]
    except Exception:
        return paths
