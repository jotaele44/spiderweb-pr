"""Bathymetry and marine spatial-evidence processing for Spiderweb.

Provides GEBCO regional subset extraction (``gebco.io``), terrain derivatives
(``gebco.terrain``), and source-agnostic marine evidence controls
(``gebco.marine_evidence``).
"""

try:
    from .io import open_gebco, subset_region
    _has_io = True
except ImportError:
    _has_io = False

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
