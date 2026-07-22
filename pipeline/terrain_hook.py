"""Terrain-elevation lookup hook (T3-30 / T5-45).

This module defines the canonical interface for terrain-context classification.
All pipeline code calls ``get_terrain_context()`` exclusively.

Contract
--------
Returns one of the following string labels:

  'urban'     — inside a known metro urban bounding box (SJU, Ponce, Mayagüez)
  'coastal'   — near sea level (DEM) or lon on the island fringe (fallback)
  'inland'    — on-island, elevated, not urban
  'offshore'  — submerged (DEM) or outside the Puerto Rico latitude band
  'unknown'   — coordinates missing or unparseable

DEM-backed classification
-------------------------
When a GEBCO NetCDF file is available — path in the ``SPIDERWEB_GEBCO_NC``
environment variable — the coastal/inland/offshore distinction is derived from
actual GEBCO elevation via :func:`gebco.terrain.classify_point`. The ``urban``
overlay (a land-use classification, not derivable from elevation) is always
applied first, and if no DEM is configured/available the original bounding-box
heuristic is used. Install the DEM stack with ``pip install -e ".[gebco]"`` and
point ``SPIDERWEB_GEBCO_NC`` at ``GEBCO_2023.nc``. The five-value vocabulary
above is stable — callers depend on it.
"""

from __future__ import annotations

import os

# Environment variable pointing at a GEBCO_2023.nc (or compatible) NetCDF file.
_GEBCO_ENV = "SPIDERWEB_GEBCO_NC"

# Cache of opened GEBCO datasets, keyed by resolved path (None = load failed).
_gebco_ds_cache: dict[str, object | None] = {}

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
    (18.35, 18.50, -66.20, -65.90),  # San Juan / Carolina metro
    (17.95, 18.07, -66.68, -66.52),  # Ponce metro
    (18.18, 18.28, -67.20, -67.08),  # Mayagüez metro
)


def _get_gebco_dataset():
    """Return an open GEBCO dataset if ``SPIDERWEB_GEBCO_NC`` points at a file.

    ``xarray`` / :func:`gebco.io.open_gebco` are imported lazily so this module
    has no hard dependency on the DEM stack; returns ``None`` when the env var is
    unset, the file is missing, or the open fails. Opened datasets are cached by
    path so the file is not re-read per call.
    """
    path = os.environ.get(_GEBCO_ENV)
    if not path or not os.path.isfile(path):
        return None
    if path not in _gebco_ds_cache:
        try:
            from gebco.io import open_gebco

            _gebco_ds_cache[path] = open_gebco(path)
        except Exception:
            _gebco_ds_cache[path] = None
    return _gebco_ds_cache[path]


def get_terrain_context(lat: float, lon: float) -> str:
    """Return the terrain context label for the given point.

    Uses GEBCO elevation for the coastal/inland/offshore distinction when a DEM
    is configured (see module docstring); otherwise falls back to the
    bounding-box heuristic. The caller contract (five-label vocabulary above) is
    stable.

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

    # Urban metro check first — a land-use overlay, not derivable from elevation,
    # so metro-edge points stay 'urban' regardless of the DEM.
    for lat_min, lat_max, lon_min, lon_max in _URBAN_BOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return "urban"

    # DEM-backed classification when a GEBCO file is configured and loadable.
    dataset = _get_gebco_dataset()
    if dataset is not None:
        try:
            from gebco.terrain import classify_point

            terrain_class = classify_point(lat, lon, dataset=dataset)
            if terrain_class in ("offshore", "coastal", "inland"):
                return terrain_class
        except Exception:
            pass  # fall through to the bbox heuristic below

    # Fallback: points outside the island's lon range but still in-lat are
    # treated as 'coastal' (sea approach / offshore island fringe), matching the
    # original bbox-based classifier in readiness/spiderweb_intake.py.
    if lon <= _PR_LON_WEST or lon >= _PR_LON_EAST:
        return "coastal"

    return "inland"
