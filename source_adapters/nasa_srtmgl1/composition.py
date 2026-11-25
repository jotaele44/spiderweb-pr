"""Per-tile source composition from SRTMGL1N NUM grids.

The shares answer "which platform measured this tile": SRTM radar (spaceborne
InSAR), ASTER GDEM2 (spaceborne optical stereo), or compiled fills such as NED
and GMTED2010. Shares are over land samples (mapped, non-water). Each tile's
3601 x 3601 samples are counted as published, including the edge rows and
columns it shares with its neighbours.
"""

from __future__ import annotations

import numpy as np

from .num_codes import CATEGORIES, LAND_CATEGORIES, classify

_PLATFORM_OF = {
    "srtm_measured": "spaceborne_insar",
    "srtm_interpolated": "spaceborne_insar",
    "aster_gdem2": "spaceborne_optical_stereo",
    "ned": "compiled",
    "gmted2010": "compiled",
    "cded": "compiled",
    "nga_undisclosed": "compiled",
}


def composition(num_grid: np.ndarray) -> dict[str, object]:
    values, counts = np.unique(num_grid, return_counts=True)
    by_category = {category: 0 for category in CATEGORIES}
    histogram = {}
    for value, count in zip(values.tolist(), counts.tolist()):
        histogram[str(value)] = count
        by_category[classify(int(value)).category] += count
    land = sum(by_category[c] for c in LAND_CATEGORIES)
    platform_counts: dict[str, int] = {}
    for category in LAND_CATEGORIES:
        platform = _PLATFORM_OF[category]
        platform_counts[platform] = platform_counts.get(platform, 0) + by_category[category]

    def pct(n: int) -> float | None:
        return round(100.0 * n / land, 4) if land else None

    return {
        "samples": int(num_grid.size),
        "land_samples": land,
        "water_samples": by_category["water"],
        "unmapped_samples": by_category["unmapped"],
        "category_counts": by_category,
        "land_share_percent": {c: pct(by_category[c]) for c in LAND_CATEGORIES},
        "platform_share_percent": {p: pct(n) for p, n in sorted(platform_counts.items())},
        "num_value_histogram": histogram,
    }
