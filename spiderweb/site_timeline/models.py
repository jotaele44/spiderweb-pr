"""Data model for the site imagery timeline.

Records are frozen dataclasses: an epoch record is never changed after it is built
(SATIM guardrail ``ORIGINAL_EPOCH_RECORD_IMMUTABILITY``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROVIDER_SCENE = "PROVIDER_SCENE"
UNDATED_BASEMAP_CAPTURE = "UNDATED_BASEMAP_CAPTURE"

VISIBLE_EPOCH_CHANGE_ONLY = "VISIBLE_EPOCH_CHANGE_ONLY"
ORIGINAL_EPOCH_RECORD_IMMUTABILITY = "ORIGINAL_EPOCH_RECORD_IMMUTABILITY"
SEPARATE_BEFORE_AFTER_PROVENANCE = "SEPARATE_BEFORE_AFTER_PROVENANCE"
NO_CAUSAL_INFERENCE = "NO_CAUSAL_INFERENCE"
GUARDRAILS = (
    VISIBLE_EPOCH_CHANGE_ONLY,
    ORIGINAL_EPOCH_RECORD_IMMUTABILITY,
    SEPARATE_BEFORE_AFTER_PROVENANCE,
    NO_CAUSAL_INFERENCE,
)
PROHIBITED_OUTPUTS = (
    "CAUSAL_INFERENCE",
    "OWNERSHIP_INFERENCE",
    "PURPOSE_INFERENCE",
    "SOURCE_RECORD_MUTATION",
)

_ENTITY_ID = re.compile(r"^ent_[a-f0-9]{32}$")

# Chip sizing and the confidence ceiling follow the site's coordinate precision.
# Both are uncalibrated heuristics: a coarse seed (2-3 decimals, roughly 100 m to
# 1 km) gets a wide chip and a low ceiling, a precise point a tight one.
COARSE_MAX_DECIMALS = 3
COARSE_CHIP_HALF_WIDTH_DEG = 0.02
PRECISE_CHIP_HALF_WIDTH_DEG = 0.005
COARSE_CONFIDENCE_CAP = 0.3
PRECISE_CONFIDENCE_CAP = 0.6


class EpochClass(str, Enum):
    SAME_EPOCH = "same_epoch"
    NEAR_EPOCH = "near_epoch"
    CROSS_EPOCH = "cross_epoch"
    UNKNOWN_EPOCH = "unknown_epoch"


class ChangeType(str, Enum):
    NEW_FEATURE = "NEW_FEATURE"
    REMOVED_FEATURE = "REMOVED_FEATURE"
    EXPANSION = "EXPANSION"
    CONTRACTION = "CONTRACTION"
    SHAPE_CHANGE = "SHAPE_CHANGE"
    SURFACE_COVER_CHANGE = "SURFACE_COVER_CHANGE"
    WATER_EXTENT_CHANGE = "WATER_EXTENT_CHANGE"
    ACCESS_CHANGE = "ACCESS_CHANGE"


class TemporalClass(str, Enum):
    STABLE = "STABLE"
    PROBABLE_CHANGE = "PROBABLE_CHANGE"
    CONFIRMED_VISIBLE_CHANGE = "CONFIRMED_VISIBLE_CHANGE"
    ARTIFACT_DRIVEN_CHANGE = "ARTIFACT_DRIVEN_CHANGE"
    INSUFFICIENT_EPOCH_ALIGNMENT = "INSUFFICIENT_EPOCH_ALIGNMENT"


@dataclass(frozen=True)
class Site:
    """A site registered by another producer. The ids are opaque data, never derived."""

    external_site_id: str
    producer_entity_id: str
    name: str
    lat: float
    lon: float
    geometry_precision_decimals: int | None = None
    authority: str | None = None

    def __post_init__(self) -> None:
        if not self.external_site_id.strip():
            raise ValueError("external_site_id is required")
        if not _ENTITY_ID.match(self.producer_entity_id):
            raise ValueError("producer_entity_id must look like ent_ plus 32 hex")
        if not (-90.0 <= self.lat <= 90.0 and -180.0 <= self.lon <= 180.0):
            raise ValueError("site coordinates out of range")

    @property
    def is_coarse(self) -> bool:
        decimals = self.geometry_precision_decimals
        return decimals is None or decimals <= COARSE_MAX_DECIMALS

    @property
    def confidence_cap(self) -> float:
        return COARSE_CONFIDENCE_CAP if self.is_coarse else PRECISE_CONFIDENCE_CAP

    def chip_bbox(self) -> tuple[float, float, float, float]:
        half = (
            COARSE_CHIP_HALF_WIDTH_DEG
            if self.is_coarse
            else PRECISE_CHIP_HALF_WIDTH_DEG
        )
        return (self.lon - half, self.lat - half, self.lon + half, self.lat + half)


@dataclass(frozen=True)
class SceneRecord:
    """One scene's metadata and content hash. Pixels are never held here."""

    scene_id: str
    provider: str
    acquired_at: str | None
    cloud_cover_pct: float | None
    resolution_m: float | None
    bbox: tuple[float, float, float, float]
    content_sha256: str
    media_type: str = "image/png"
    platform: str = "unknown"
    instrument: str = "unknown"
    collection: str = "unknown"
    capture_kind: str = PROVIDER_SCENE
    geometric_confidence: float = 0.6
    synthetic: bool = False
    source_uri: str | None = None


@dataclass(frozen=True)
class EpochRecord:
    record_id: str
    epoch_id: str
    capture_time: str
    provider: str
    resolution_m: float | None
    geometry_id: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TemporalObservation:
    comparison_id: str
    before: EpochRecord
    after: EpochRecord
    change_signals: dict[str, float]
    spatial_overlap: float = 1.0
    registration_quality: float = 1.0
    scale_compatibility: float = 1.0
    view_angle_compatibility: float = 1.0
    artifact_confidence: float = 0.0
    contradiction_confidence: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class TemporalScore:
    comparison_id: str
    classification: str
    change_score: float
    alignment_score: float
    artifact_confidence: float
    contradiction_confidence: float
    adjusted_change_score: float
    change_types: tuple[str, ...]
    review_required: bool
    review_reasons: tuple[str, ...]
