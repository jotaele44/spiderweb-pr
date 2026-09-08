"""Federation-safe land/ocean surface-analysis result primitives.

Spiderweb owns geometry computation.  Consumers receive immutable, hashed
results and never need access to Spiderweb's raster store.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
import re
from typing import Any

CONTRACT_VERSION = "spatial-analysis-result/1.0"
ENGINE_AUTHORITY = "spiderweb-pr"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class SurfaceClass(StrEnum):
    LAND_ELEVATION = "LAND_ELEVATION"
    COASTAL_TOPOBATHY = "COASTAL_TOPOBATHY"
    OCEAN_DEPTH = "OCEAN_DEPTH"


class MeasurementClass(StrEnum):
    DIRECT_MULTIBEAM = "DIRECT_MULTIBEAM"
    DIRECT_SINGLE_BEAM = "DIRECT_SINGLE_BEAM"
    SATELLITE_DERIVED = "SATELLITE_DERIVED"
    INTERPOLATED = "INTERPOLATED"
    MODELED = "MODELED"
    CARTOGRAPHIC_RENDER = "CARTOGRAPHIC_RENDER"


class SpatialState(StrEnum):
    FULLY_WITHIN = "FULLY_WITHIN"
    PARTIAL = "PARTIAL"
    TOUCH_ONLY = "TOUCH_ONLY"
    OUTSIDE = "OUTSIDE"
    NULL_EMPTY = "NULL_EMPTY"
    UNRESOLVED = "UNRESOLVED"


class IdentityState(StrEnum):
    AUTHORITATIVE_BINDING = "AUTHORITATIVE_BINDING"
    CANDIDATE_NOT_IDENTITY = "CANDIDATE_NOT_IDENTITY"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ResolutionSummary:
    best_m: float | None
    worst_m: float | None
    dominant_m: float | None
    direct_coverage_fraction: float
    interpolated_fraction: float
    nodata_fraction: float

    def __post_init__(self) -> None:
        for name in ("direct_coverage_fraction", "interpolated_fraction", "nodata_fraction"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.direct_coverage_fraction + self.interpolated_fraction + self.nodata_fraction > 1.000001:
            raise ValueError("coverage fractions must not exceed 1")
        known = [v for v in (self.best_m, self.worst_m, self.dominant_m) if v is not None]
        if any(v <= 0 or not math.isfinite(v) for v in known):
            raise ValueError("known resolutions must be positive finite metres")
        if self.best_m is not None and self.worst_m is not None and self.best_m > self.worst_m:
            raise ValueError("best_m must not exceed worst_m")


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SpatialAnalysisResult:
    analysis_id: str
    query_id: str
    subject_type: str
    subject_id: str
    subject_manifestation_id: str
    geometry_role: str
    input_geometry_hash: str
    target_domain: str
    spatial_state: SpatialState
    identity_state: IdentityState
    source_manifestation_ids: tuple[str, ...]
    measurement_classes: tuple[MeasurementClass, ...]
    resolution_summary: ResolutionSummary
    analysis_engine_version: str
    crs_operation: str
    horizontal_source_crs: str
    horizontal_computation_crs: str
    vertical_datum: str | None
    depth_sign_convention: str
    units: str = "metres"
    producer_repo: str = ENGINE_AUTHORITY
    contract_version: str = CONTRACT_VERSION
    input_time_start: str | None = None
    input_time_end: str | None = None
    target_feature_id: str | None = None
    target_candidate_id: str | None = None
    distance_m: float | None = None
    intersection_length_m: float | None = None
    intersection_area_m2: float | None = None
    surface_depth_min_m: float | None = None
    surface_depth_max_m: float | None = None
    surface_depth_mean_m: float | None = None
    slope_max_deg: float | None = None
    local_relief_m: float | None = None
    confidence_state: str = "UNRESOLVED"
    analysis_timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        required = (self.analysis_id, self.query_id, self.subject_type, self.subject_id,
                    self.subject_manifestation_id, self.geometry_role, self.target_domain,
                    self.analysis_engine_version, self.crs_operation,
                    self.horizontal_source_crs, self.horizontal_computation_crs)
        if any(not item.strip() for item in required):
            raise ValueError("required identifiers and CRS fields must not be empty")
        if not _SHA256.fullmatch(self.input_geometry_hash):
            raise ValueError("input_geometry_hash must be a lowercase SHA-256")
        if not self.source_manifestation_ids or len(set(self.source_manifestation_ids)) != len(self.source_manifestation_ids):
            raise ValueError("source_manifestation_ids must be non-empty and unique")
        if not self.measurement_classes or len(set(self.measurement_classes)) != len(self.measurement_classes):
            raise ValueError("measurement_classes must be non-empty and unique")
        if self.target_feature_id and self.target_candidate_id:
            raise ValueError("canonical target and candidate target are mutually exclusive")
        if self.target_candidate_id and self.identity_state is not IdentityState.CANDIDATE_NOT_IDENTITY:
            raise ValueError("candidate targets must remain CANDIDATE_NOT_IDENTITY")
        if self.vertical_datum is None and any(v is not None for v in (
            self.surface_depth_min_m, self.surface_depth_max_m, self.surface_depth_mean_m)):
            raise ValueError("quantitative depth requires an explicit vertical datum")
        if self.depth_sign_convention not in {"positive_up", "positive_down"}:
            raise ValueError("depth_sign_convention must be explicit")
        if self.units != "metres":
            raise ValueError("contract 1.0 serializes distances and depths in metres")
        if self.spatial_state is SpatialState.NULL_EMPTY and any(v is not None for v in (
            self.distance_m, self.intersection_length_m, self.intersection_area_m2,
            self.surface_depth_min_m, self.surface_depth_max_m, self.surface_depth_mean_m)):
            raise ValueError("NULL_EMPTY cannot carry synthesized measurements")
        for value in (self.distance_m, self.intersection_length_m, self.intersection_area_m2, self.local_relief_m):
            if value is not None and (value < 0 or not math.isfinite(value)):
                raise ValueError("distance, intersection and relief values must be non-negative finite numbers")

    def as_artifact(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["spatial_state"] = self.spatial_state.value
        payload["identity_state"] = self.identity_state.value
        payload["measurement_classes"] = [v.value for v in self.measurement_classes]
        payload["source_manifestation_ids"] = list(self.source_manifestation_ids)
        payload["result_hash"] = _canonical_hash(payload)
        return payload

    @staticmethod
    def verify_artifact(artifact: dict[str, Any]) -> bool:
        supplied = artifact.get("result_hash")
        payload = {k: v for k, v in artifact.items() if k != "result_hash"}
        return isinstance(supplied, str) and _SHA256.fullmatch(supplied) is not None and supplied == _canonical_hash(payload)
