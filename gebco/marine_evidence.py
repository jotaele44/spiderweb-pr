"""Marine spatial-evidence primitives for Spiderweb.

This module is deliberately source-agnostic: GEBCO, NOAA hydrography, lidar,
sonar and other bathymetric products can all be represented without treating a
rendered/derived product as a direct observation.  It provides the hard gates
needed before cross-sensor or temporal depth comparisons are promoted to
findings.

All depths are expressed in metres.  No-data is represented by ``None``;
``0.0`` is a valid observation and is never treated as no-data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import sqrt
from typing import Iterable, Mapping


class SensorType(StrEnum):
    MULTIBEAM_ECHOSOUNDER = "MULTIBEAM_ECHOSOUNDER"
    SINGLE_BEAM_ECHOSOUNDER = "SINGLE_BEAM_ECHOSOUNDER"
    BATHYMETRIC_LIDAR = "BATHYMETRIC_LIDAR"
    TOPOBATHYMETRIC_LIDAR = "TOPOBATHYMETRIC_LIDAR"
    SATELLITE_DERIVED_BATHYMETRY = "SATELLITE_DERIVED_BATHYMETRY"
    HYDROGRAPHIC_SOUNDINGS = "HYDROGRAPHIC_SOUNDINGS"
    SIDE_SCAN_SONAR = "SIDE_SCAN_SONAR"
    SONAR_BACKSCATTER = "SONAR_BACKSCATTER"
    SUBBOTTOM_PROFILER = "SUBBOTTOM_PROFILER"
    SEISMIC_REFLECTION = "SEISMIC_REFLECTION"
    ROV = "ROV"
    AUV = "AUV"
    COASTAL_DEM = "COASTAL_DEM"
    NAUTICAL_CHART = "NAUTICAL_CHART"
    DERIVED_BATHYMETRIC_GRID = "DERIVED_BATHYMETRIC_GRID"
    VISUALIZATION = "VISUALIZATION"


class ProductStage(StrEnum):
    RAW_OBSERVATION = "RAW_OBSERVATION"
    PROCESSED_OBSERVATION = "PROCESSED_OBSERVATION"
    GRID = "GRID"
    DERIVED_PRODUCT = "DERIVED_PRODUCT"
    VISUALIZATION = "VISUALIZATION"


class CoverageState(StrEnum):
    DIRECTLY_OBSERVED = "DIRECTLY_OBSERVED"
    INTERPOLATED = "INTERPOLATED"
    EXTRAPOLATED = "EXTRAPOLATED"
    REMOTE_DERIVED = "REMOTE_DERIVED"
    GENERALIZED = "GENERALIZED"
    NULL_EMPTY = "NULL_EMPTY"
    UNKNOWN = "UNKNOWN"


class EvidenceState(StrEnum):
    DIRECT_SENSOR_CONFIRMED = "DIRECT_SENSOR_CONFIRMED"
    MULTISENSOR_CONFIRMED = "MULTISENSOR_CONFIRMED"
    SINGLE_SENSOR_SUPPORTED = "SINGLE_SENSOR_SUPPORTED"
    DERIVED_ONLY = "DERIVED_ONLY"
    INTERPOLATED_ONLY = "INTERPOLATED_ONLY"
    VISUALIZATION_ONLY = "VISUALIZATION_ONLY"
    ARTIFACT_CANDIDATE = "ARTIFACT_CANDIDATE"
    NO_SENSOR_COVERAGE = "NO_SENSOR_COVERAGE"
    UNRESOLVED = "UNRESOLVED"


class GeomorphologyClass(StrEnum):
    SHELF = "SHELF"
    SHELF_BREAK = "SHELF_BREAK"
    SLOPE = "SLOPE"
    BASIN = "BASIN"
    TROUGH = "TROUGH"
    CANYON = "CANYON"
    CHANNEL = "CHANNEL"
    GULLY = "GULLY"
    RIDGE = "RIDGE"
    MOUND = "MOUND"
    DEPRESSION = "DEPRESSION"
    ESCARPMENT = "ESCARPMENT"
    TERRACE = "TERRACE"
    BANK = "BANK"
    SHOAL = "SHOAL"
    REEF = "REEF"
    HARDBOTTOM = "HARDBOTTOM"
    SEDIMENT_WAVE = "SEDIMENT_WAVE"
    SLUMP = "SLUMP"
    LANDSLIDE = "LANDSLIDE"
    DEBRIS_FIELD = "DEBRIS_FIELD"
    SCOUR = "SCOUR"
    DREDGED_CHANNEL = "DREDGED_CHANNEL"
    DREDGE_SPOIL = "DREDGE_SPOIL"
    EXCAVATION = "EXCAVATION"
    LINEAR_FEATURE = "LINEAR_FEATURE"
    CIRCULAR_FEATURE = "CIRCULAR_FEATURE"
    ANOMALOUS_MORPHOLOGY = "ANOMALOUS_MORPHOLOGY"
    UNRESOLVED_MORPHOLOGY = "UNRESOLVED_MORPHOLOGY"


@dataclass(frozen=True, slots=True)
class VerticalReference:
    """Horizontal/vertical reference identity for a depth observation.

    Empty or unknown fields intentionally prevent exact compatibility.  Depth
    sign is explicit because many bathymetric grids use negative elevation
    while hydrographic products use positive depth.
    """

    horizontal_crs: str
    vertical_crs: str | None
    vertical_datum: str | None
    tidal_datum: str | None
    depth_positive: str = "down"

    def __post_init__(self) -> None:
        if self.depth_positive not in {"up", "down"}:
            raise ValueError("depth_positive must be 'up' or 'down'")
        if not self.horizontal_crs.strip():
            raise ValueError("horizontal_crs must not be empty")

    @property
    def key(self) -> tuple[str, str | None, str | None, str | None, str]:
        return (
            self.horizontal_crs,
            self.vertical_crs,
            self.vertical_datum,
            self.tidal_datum,
            self.depth_positive,
        )

    def is_fully_bound(self) -> bool:
        return bool(self.vertical_crs or self.vertical_datum or self.tidal_datum)

    def exactly_compatible_with(self, other: "VerticalReference") -> bool:
        return self.is_fully_bound() and other.is_fully_bound() and self.key == other.key


@dataclass(frozen=True, slots=True)
class DepthTransform:
    """Explicit, externally certified transformation between vertical references."""

    source: VerticalReference
    target: VerticalReference
    scale: float = 1.0
    offset_m: float = 0.0
    authority: str = ""

    def __post_init__(self) -> None:
        if not self.authority.strip():
            raise ValueError("transform authority/binding must be supplied")
        if self.scale == 0:
            raise ValueError("transform scale must be non-zero")

    def apply(self, value_m: float) -> float:
        return value_m * self.scale + self.offset_m


@dataclass(frozen=True, slots=True)
class MarineObservation:
    observation_id: str
    sensor: SensorType
    stage: ProductStage
    root_survey_id: str | None
    vertical_reference: VerticalReference
    coverage: CoverageState
    value_m: float | None = None
    uncertainty_m: float | None = None
    observed_at: datetime | None = None
    parent_ids: tuple[str, ...] = ()
    source_uri: str | None = None
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id must not be empty")
        if self.uncertainty_m is not None and self.uncertainty_m < 0:
            raise ValueError("uncertainty_m must be non-negative")
        if self.observation_id in self.parent_ids:
            raise ValueError("an observation cannot be its own parent")

    @property
    def has_value(self) -> bool:
        return self.value_m is not None

    @property
    def is_direct_sensor_observation(self) -> bool:
        return (
            self.stage in {ProductStage.RAW_OBSERVATION, ProductStage.PROCESSED_OBSERVATION}
            and self.coverage is CoverageState.DIRECTLY_OBSERVED
            and self.sensor is not SensorType.VISUALIZATION
        )


class VerticalCompatibilityError(ValueError):
    """Raised when a quantitative depth comparison is not datum-safe."""


@dataclass(frozen=True, slots=True)
class DepthComparison:
    observation_a: str
    observation_b: str
    delta_b_minus_a_m: float
    combined_uncertainty_m: float | None
    transform_authority: str | None


def _find_transform(
    source: VerticalReference,
    target: VerticalReference,
    transforms: Iterable[DepthTransform],
) -> DepthTransform | None:
    for transform in transforms:
        if transform.source.key == source.key and transform.target.key == target.key:
            return transform
    return None


def compare_depths(
    a: MarineObservation,
    b: MarineObservation,
    *,
    transforms: Iterable[DepthTransform] = (),
) -> DepthComparison:
    """Compare two colocated/aligned depths after a strict vertical-reference gate.

    Spatial colocation/grid alignment is intentionally a caller responsibility;
    this function only certifies the vertical-reference and numerical portions.
    """

    if a.value_m is None or b.value_m is None:
        raise ValueError("depth comparison requires two non-null values")

    transform_authority: str | None = None
    b_value = b.value_m
    if not a.vertical_reference.exactly_compatible_with(b.vertical_reference):
        transform = _find_transform(b.vertical_reference, a.vertical_reference, transforms)
        if transform is None:
            raise VerticalCompatibilityError(
                "vertical references differ or are insufficiently bound; "
                "an explicit certified transform is required"
            )
        b_value = transform.apply(b_value)
        transform_authority = transform.authority

    combined = None
    if a.uncertainty_m is not None and b.uncertainty_m is not None:
        combined = sqrt(a.uncertainty_m**2 + b.uncertainty_m**2)

    return DepthComparison(
        observation_a=a.observation_id,
        observation_b=b.observation_id,
        delta_b_minus_a_m=b_value - a.value_m,
        combined_uncertainty_m=combined,
        transform_authority=transform_authority,
    )


def independent_root_ids(observations: Iterable[MarineObservation]) -> frozenset[str]:
    """Return distinct acquisition roots; missing roots never manufacture independence."""

    return frozenset(
        obs.root_survey_id
        for obs in observations
        if obs.root_survey_id is not None and obs.root_survey_id.strip()
    )


def lineage_independence_count(observations: Iterable[MarineObservation]) -> int:
    return len(independent_root_ids(observations))


def classify_feature_evidence(
    observations: Iterable[MarineObservation],
    *,
    artifact_flags: Iterable[str] = (),
) -> EvidenceState:
    """Classify feature support without double-counting derivative manifestations.

    Multisensor confirmation requires at least two *direct* observations from
    different acquisition roots and different sensor types.  A DEM, chart,
    hillshade and visualization derived from one survey therefore remain one
    lineage, not four confirmations.
    """

    obs = tuple(observations)
    flags = tuple(flag for flag in artifact_flags if flag)
    if not obs:
        return EvidenceState.NO_SENSOR_COVERAGE

    direct = tuple(item for item in obs if item.is_direct_sensor_observation)
    direct_roots = independent_root_ids(direct)
    direct_sensors = {item.sensor for item in direct}

    if len(direct_roots) >= 2 and len(direct_sensors) >= 2:
        return EvidenceState.MULTISENSOR_CONFIRMED
    if direct:
        if len(direct_roots) == 1:
            return EvidenceState.SINGLE_SENSOR_SUPPORTED
        return EvidenceState.DIRECT_SENSOR_CONFIRMED

    if flags:
        return EvidenceState.ARTIFACT_CANDIDATE

    if all(item.coverage is CoverageState.NULL_EMPTY for item in obs):
        return EvidenceState.NO_SENSOR_COVERAGE
    if all(item.stage is ProductStage.VISUALIZATION for item in obs):
        return EvidenceState.VISUALIZATION_ONLY
    if all(
        item.coverage in {CoverageState.INTERPOLATED, CoverageState.EXTRAPOLATED}
        for item in obs
    ):
        return EvidenceState.INTERPOLATED_ONLY
    if any(
        item.stage in {ProductStage.GRID, ProductStage.DERIVED_PRODUCT}
        or item.coverage in {CoverageState.REMOTE_DERIVED, CoverageState.GENERALIZED}
        for item in obs
    ):
        return EvidenceState.DERIVED_ONLY
    return EvidenceState.UNRESOLVED


def validate_lineage(records: Mapping[str, MarineObservation]) -> None:
    """Validate parent references and reject lineage cycles.

    Parentless source records are allowed.  Unknown parent IDs fail closed so a
    derivative cannot silently lose its provenance chain.
    """

    for record in records.values():
        missing = [parent for parent in record.parent_ids if parent not in records]
        if missing:
            raise ValueError(
                f"{record.observation_id}: unknown lineage parent(s): {missing}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise ValueError(f"lineage cycle detected at {node_id}")
        visiting.add(node_id)
        for parent in records[node_id].parent_ids:
            visit(parent)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in records:
        visit(node_id)


def source_lineage_roots(
    record_id: str, records: Mapping[str, MarineObservation]
) -> frozenset[str]:
    """Resolve terminal lineage records for audit/debug use."""

    if record_id not in records:
        raise KeyError(record_id)
    validate_lineage(records)

    roots: set[str] = set()

    def walk(node_id: str) -> None:
        node = records[node_id]
        if not node.parent_ids:
            roots.add(node_id)
            return
        for parent in node.parent_ids:
            walk(parent)

    walk(record_id)
    return frozenset(roots)
