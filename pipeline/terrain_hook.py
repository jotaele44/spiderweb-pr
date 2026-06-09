"""Terrain-elevation lookup hook — stub interface (T3-30 / T5-45).

This module defines the canonical interface for terrain-context classification.
All pipeline code calls ``get_terrain_context()`` exclusively; real DEM-backed
implementations replace only this module's body.

Stub contract
-------------
Returns one of the following string labels:

  'urban'     — inside a known metro urban bounding box (SJU, Ponce, Mayagüez)
  'coastal'   — lon ≤ PR_LON_WEST+0.1 or lon ≥ PR_LON_EAST-0.1 and lat in PR
  'inland'    — on-island, not urban, not coastal
  'offshore'  — outside Puerto Rico bounding box
  'unknown'   — coordinates missing or unparseable

Upgrade path
------------
To wire in the GEBCO/SRTM DEM:

1. Install the ``gebco`` extra: ``pip install -e ".[gebco]"``
2. Call ``gebco.terrain.classify_point(lat, lon)`` in the function body below,
   returning its 'terrain_class' value (same vocabulary).
3. Remove or re-purpose the bounding-box fallback.

The interface itself must not change — callers depend on the five-value enum above.
"""
from __future__ import annotations

# Puerto Rico bounding box constants (shared with mbil.py).
# Latitude range is slightly generous so coastal/border points don't get
# mis-classified as offshore.
_PR_LAT_MIN: float = 17.80
_PR_LAT_MAX: float = 18.60
_PR_LON_WEST: float = -67.30
_PR_LON_EAST: float = -65.50

# Metro urban bounding boxes: (lat_min, lat_max, lon_min, lon_max).
# Bounds match the URBAN_*/PONCE_URBAN_*/MAYAGUEZ_URBAN_* constants in
# readiness/spiderweb_intake.py — keep them in sync.
_URBAN_BOXES = (
    (18.35, 18.50, -66.20, -65.90),   # San Juan / Carolina metro
    (17.95, 18.07, -66.68, -66.52),   # Ponce metro
    (18.18, 18.28, -67.20, -67.08),   # Mayagüez metro
)


def get_terrain_context(lat: float, lon: float) -> str:
    """Return the terrain context label for the given point.

    This is the canonical hook. Replace the body when a real DEM is available;
    the caller contract (five-label vocabulary above) must remain stable.

    Args:
        lat: Latitude in decimal degrees (WGS-84).
        lon: Longitude in decimal degrees (WGS-84).

    Returns:
        One of ``'urban'``, ``'coastal'``, ``'inland'``, ``'offshore'``,
        or ``'unknown'``.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return "unknown"

    # True offshore — outside latitude band entirely.
    if not (_PR_LAT_MIN <= lat <= _PR_LAT_MAX):
        return "offshore"

    # Urban metro check before coastal so metro-edge points stay 'urban'.
    for lat_min, lat_max, lon_min, lon_max in _URBAN_BOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return "urban"

    # Points outside the island's lon range but still in-lat are treated as
    # 'coastal' (sea approach / offshore island fringe), matching the original
    # bbox-based classifier in readiness/spiderweb_intake.py.
    if lon <= _PR_LON_WEST or lon >= _PR_LON_EAST:
        return "coastal"

    return "inland"
