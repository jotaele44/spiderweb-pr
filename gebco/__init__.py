"""Bathymetry and marine spatial-evidence processing for Spiderweb.

Provides GEBCO regional subset extraction (``gebco.io``), terrain derivatives
(``gebco.terrain``), and source-agnostic marine evidence controls
(``gebco.marine_evidence``).

Only ``gebco.marine_evidence`` (standard library only) is imported eagerly. The
``gebco.terrain`` names (numpy, scipy) and the ``gebco.io`` names (xarray) load on
first use through the module ``__getattr__`` below. That keeps
``gebco.marine_evidence`` importable without the raster stack, which the
access-point lane of ``scripts/federation_export.py`` relies on: the hub runs that
export with only its own packages installed.
"""

from __future__ import annotations

from typing import Any

from .marine_evidence import (
    CoverageState,
    DepthComparison,
    DepthTransform,
    EvidenceState,
    GeomorphologyClass,
    MarineObservation,
    ProductStage,
    SensorType,
    VerticalCompatibilityError,
    VerticalReference,
    classify_feature_evidence,
    compare_depths,
    independent_root_ids,
    lineage_independence_count,
    source_lineage_roots,
    validate_lineage,
)

_TERRAIN_NAMES = frozenset(
    {
        "PR_LAT_MAX",
        "PR_LAT_MIN",
        "PR_LON_MAX",
        "PR_LON_MIN",
        "bbox_intersects_pr",
        "cell_size_meters",
        "clip_to_bbox",
        "compute_curvatures",
        "compute_roughness",
        "compute_rugosity",
        "compute_slope",
    }
)
_IO_NAMES = frozenset({"open_gebco", "subset_region"})


def __getattr__(name: str) -> Any:
    """PEP 562: load the raster-stack modules on first use."""
    if name in _TERRAIN_NAMES:
        from . import terrain

        return getattr(terrain, name)
    if name in _IO_NAMES:
        from . import io

        return getattr(io, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "SensorType",
    "ProductStage",
    "CoverageState",
    "EvidenceState",
    "GeomorphologyClass",
    "VerticalReference",
    "DepthTransform",
    "MarineObservation",
    "VerticalCompatibilityError",
    "DepthComparison",
    "compare_depths",
    "independent_root_ids",
    "lineage_independence_count",
    "classify_feature_evidence",
    "validate_lineage",
    "source_lineage_roots",
]
