"""GEBCO 2023 bathymetry processing pipeline.

Provides regional subset extraction (``gebco.io``) and terrain-derivative
computation (``gebco.terrain``) for the GEBCO 2023 global 15 arc-second grid.
"""

try:
    from .io import open_gebco, subset_region
    _has_io = True
except ImportError:
    _has_io = False

from .terrain import (
    PR_LAT_MAX,
    PR_LAT_MIN,
    PR_LON_MAX,
    PR_LON_MIN,
    bbox_intersects_pr,
    cell_size_meters,
    clip_to_bbox,
    compute_curvatures,
    compute_roughness,
    compute_rugosity,
    compute_slope,
)

__all__ = [
    "open_gebco",
    "subset_region",
    "PR_LON_MIN",
    "PR_LON_MAX",
    "PR_LAT_MIN",
    "PR_LAT_MAX",
    "bbox_intersects_pr",
    "clip_to_bbox",
    "cell_size_meters",
    "compute_slope",
    "compute_curvatures",
    "compute_roughness",
    "compute_rugosity",
]
