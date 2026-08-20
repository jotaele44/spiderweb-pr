"""Reusable AOI-driven subsurface relevance analysis.

The subsystem is intentionally evidence-conservative: spatial proximity is discovery,
not identity or connectivity proof. See docs/SUBSURFACE_AOI_SKILL.md.
"""

from .aoi import FrozenAOI, freeze_aoi
from .evidence import (
    EvidenceRecord,
    EvidenceTier,
    SpatialState,
    adjudicate_feature,
    validate_records,
)

__all__ = [
    "EvidenceRecord",
    "EvidenceTier",
    "FrozenAOI",
    "SpatialState",
    "adjudicate_feature",
    "freeze_aoi",
    "validate_records",
]
