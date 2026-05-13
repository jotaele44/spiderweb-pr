"""GEBCO 2023 bathymetry processing pipeline.

Provides regional subset extraction (``gebco.io``) and terrain-derivative
computation (``gebco.terrain``) for the GEBCO 2023 global 15 arc-second grid.
"""

from .io import open_gebco, subset_region
from .terrain import (
    cell_size_meters,
    compute_curvatures,
    compute_roughness,
    compute_rugosity,
    compute_slope,
)

__all__ = [
    "open_gebco",
    "subset_region",
    "cell_size_meters",
    "compute_slope",
    "compute_curvatures",
    "compute_roughness",
    "compute_rugosity",
]
