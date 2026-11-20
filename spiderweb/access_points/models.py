"""Record models for the access-point registries.

Six identities are kept apart and never derived from one another:

==========================  =====================================================
source manifestation        one exact published thing (file, service response)
original observation        one record inside one source manifestation
physical feature            the registry's statement that something exists
derived geometry            a shape computed from observations by a method
relationship                a typed, evidenced link between two records
historical continuity       ``supersedes`` links between feature records
==========================  =====================================================

All models are immutable.  ``to_dict`` output is canonical JSON-safe and is what
the registries persist and hash.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Mapping

from federation.spatial_core import canonical_json_sha256, validate_lon_lat
from gebco.marine_evidence import (
    CoverageState,
    ProductStage,
    SensorType,
    VerticalReference,
)

from .namespaces import (
    Namespace,
    TypedRef,
    is_feature_id,
    is_geometry_id,
    is_observation_id,
    is_relationship_id,
    is_source_id,
    require_registry_namespace,
)
from .vocabulary import (
    AdjudicationStatus,
    ClaimClass,
    ConnectivityKind,
    EvidenceDimension,
    EvidenceTier,
    GeometryBasis,
    InlandFeatureClass,
    OffshoreFeatureClass,
    Origin,
    ProvenanceState,
    RegistryStatus,
    RelationshipType,
)

HORIZONTAL_INTERCHANGE_CRS = "OGC:CRS84"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GEOMETRY_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
}

FEATURE_CLASSES: dict[Namespace, type[Enum]] = {
    Namespace.ACCESS_POINT_INLAND: InlandFeatureClass,
    Namespace.ACCESS_POINT_OFFSHORE: OffshoreFeatureClass,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, TypedRef):
        return {"namespace": value.namespace.value, "identifier": value.identifier}
    if isinstance(value, VerticalReference):
        return {
            "horizontal_crs": value.horizontal_crs,
            "vertical_crs": value.vertical_crs,
            "vertical_datum": value.vertical_datum,
            "tidal_datum": value.tidal_datum,
            "depth_positive": value.depth_positive,
        }
    if isinstance(value, EvidenceTier):
        return value.name
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers cannot be stored")
    return value


class _Record:
    """Shared ``to_dict`` / hashing for the frozen record dataclasses."""

    def to_dict(self) -> dict[str, Any]:
        return {f.name: _jsonable(getattr(self, f.name)) for f in fields(self)}  # type: ignore[arg-type]

    def logical_sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


def validate_geometry(geometry: Mapping[str, Any]) -> None:
    """Validate a GeoJSON geometry in lon/lat order.  Raises ``ValueError``."""

    if not isinstance(geometry, Mapping):
        raise ValueError("geometry must be a GeoJSON geometry object")
    gtype = geometry.get("type")
    if gtype not in _GEOMETRY_TYPES:
        raise ValueError(f"unsupported geometry type: {gtype!r}")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) == 0:
        raise ValueError("geometry has no coordinates")
    seen = 0

    def walk(node: Any) -> None:
        nonlocal seen
        if (
            isinstance(node, (list, tuple))
            and len(node) >= 2
            and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in node
            )
        ):
            validate_lon_lat(node[0], node[1])
            if len(node) > 3:
                raise ValueError("positions carry at most three ordinates")
            if len(node) == 3 and not math.isfinite(float(node[2])):
                raise ValueError("vertical ordinate must be finite")
            seen += 1
            return
        if not isinstance(node, (list, tuple)) or len(node) == 0:
            raise ValueError("malformed geometry coordinates")
        for child in node:
            walk(child)

    walk(coordinates)
    if seen == 0:
        raise ValueError("geometry has no positions")


def _require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_tuple(value: Any, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")


@dataclass(frozen=True)
class SourceManifestation(_Record):
    """One exact published source.  Identity is the content, not the name."""

    source_id: str
    provider: str
    title: str
    native_identifier: str | None = None
    source_uri: str | None = None
    manifestation_sha256: str | None = None
    retrieved_utc: str | None = None
    published_date: str | None = None
    survey_date: str | None = None
    lineage_root_id: str | None = None
    parent_source_ids: tuple[str, ...] = ()
    product_stage: ProductStage = ProductStage.DERIVED_PRODUCT
    sensor_type: SensorType | None = None
    coverage_state: CoverageState = CoverageState.UNKNOWN
    provenance_state: ProvenanceState = ProvenanceState.UNREGISTERED
    license_note: str | None = None

    def __post_init__(self) -> None:
        if not is_source_id(self.source_id):
            raise ValueError("source_id must be an APSRC identifier")
        _require_text(self.provider, "provider")
        _require_text(self.title, "title")
        _require_tuple(self.parent_source_ids, "parent_source_ids")
        if self.source_id in self.parent_source_ids:
            raise ValueError("a source cannot be its own parent")
        if self.manifestation_sha256 is not None and not _SHA256_RE.match(
            self.manifestation_sha256
        ):
            raise ValueError("manifestation_sha256 must be 64 lowercase hex characters")
        if self.provenance_state is ProvenanceState.REGISTERED:
            if not self.manifestation_sha256:
                raise ValueError(
                    "a REGISTERED source needs the SHA-256 of its exact bytes"
                )
            _require_text(self.retrieved_utc, "retrieved_utc")
        if self.provenance_state is ProvenanceState.REFERENCED_ONLY and not (
            self.native_identifier or self.source_uri
        ):
            raise ValueError(
                "a REFERENCED_ONLY source needs a stable identifier or URI"
            )

    @property
    def is_direct_measurement(self) -> bool:
        """True only for a held, hashed, rooted sensor observation product.

        A grid, a fused DEM, an inventory footprint, a rendering or anything
        whose bytes are not held is not a direct measurement.
        """

        return (
            self.provenance_state is ProvenanceState.REGISTERED
            and self.product_stage
            in {ProductStage.RAW_OBSERVATION, ProductStage.PROCESSED_OBSERVATION}
            and self.coverage_state is CoverageState.DIRECTLY_OBSERVED
            and self.sensor_type is not None
            and self.sensor_type is not SensorType.VISUALIZATION
            and bool(self.lineage_root_id and self.lineage_root_id.strip())
        )


@dataclass(frozen=True)
class Observation(_Record):
    """One original record, kept as the source stated it."""

    observation_id: str
    namespace: Namespace
    source_id: str
    native_record_id: str
    geometry_basis: GeometryBasis
    raw_label: str | None = None
    raw_attributes: Mapping[str, Any] = field(default_factory=dict)
    geometry: Mapping[str, Any] | None = None
    horizontal_crs: str | None = None
    horizontal_uncertainty_m: float | None = None
    value_m: float | None = None
    vertical_reference: VerticalReference | None = None
    vertical_uncertainty_m: float | None = None
    observed_date: str | None = None
    discovered_utc: str | None = None
    claim_class: ClaimClass = ClaimClass.UNKNOWN
    locality_label: str | None = None

    def __post_init__(self) -> None:
        require_registry_namespace(self.namespace)
        if not is_observation_id(self.observation_id, self.namespace):
            raise ValueError(
                "observation_id does not belong to this registry namespace"
            )
        if not is_source_id(self.source_id):
            raise ValueError("source_id must be an APSRC identifier")
        _require_text(self.native_record_id, "native_record_id")
        no_geometry_bases = {GeometryBasis.LOCALITY_LABEL_ONLY, GeometryBasis.NONE}
        if self.geometry is None:
            if self.geometry_basis not in no_geometry_bases:
                raise ValueError(
                    "an observation without geometry must say so: geometry_basis "
                    "LOCALITY_LABEL_ONLY or NONE"
                )
            if (
                self.horizontal_crs is not None
                or self.horizontal_uncertainty_m is not None
            ):
                raise ValueError(
                    "CRS and horizontal uncertainty are meaningless without geometry"
                )
        else:
            if self.geometry_basis in no_geometry_bases:
                raise ValueError(
                    "coordinates cannot be attached to a locality-label observation; "
                    "register a source that actually carries them"
                )
            validate_geometry(self.geometry)
            if self.horizontal_crs != HORIZONTAL_INTERCHANGE_CRS:
                raise ValueError(
                    f"stored geometry must be {HORIZONTAL_INTERCHANGE_CRS}; reproject "
                    "explicitly and keep the native CRS in raw_attributes"
                )
        if self.geometry_basis is GeometryBasis.LOCALITY_LABEL_ONLY:
            _require_text(self.locality_label, "locality_label")
        for name in ("horizontal_uncertainty_m", "vertical_uncertainty_m"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.value_m is not None:
            if not math.isfinite(self.value_m):
                raise ValueError("value_m must be finite")
            if self.vertical_reference is None:
                raise ValueError(
                    "a vertical value without a vertical reference is not a measurement"
                )
        elif self.vertical_uncertainty_m is not None:
            raise ValueError("vertical uncertainty without a vertical value")


@dataclass(frozen=True)
class EvidenceAssertion(_Record):
    """One statement about one evidence dimension of one feature."""

    dimension: EvidenceDimension
    tier: EvidenceTier
    claim_class: ClaimClass
    basis: tuple[str, ...]
    statement: str
    observation_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    method: str | None = None
    method_version: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    adjudication: AdjudicationStatus = AdjudicationStatus.UNREVIEWED
    adjudicated_by: str | None = None
    adjudicated_utc: str | None = None
    connectivity_kind: ConnectivityKind | None = None
    origin: Origin | None = None

    def __post_init__(self) -> None:
        _require_text(self.statement, "statement")
        for name in ("basis", "observation_ids", "source_ids"):
            _require_tuple(getattr(self, name), name)
        if any(not isinstance(b, str) or not b.strip() for b in self.basis):
            raise ValueError("basis entries must be non-empty strings")
        if any(not is_source_id(s) for s in self.source_ids):
            raise ValueError("source_ids must be APSRC identifiers")
        if self.dimension is EvidenceDimension.CONNECTIVITY:
            if self.connectivity_kind is None:
                raise ValueError(
                    "a CONNECTIVITY assertion must name which kind of connection it means"
                )
        elif self.connectivity_kind is not None:
            raise ValueError(
                "connectivity_kind is only valid on the CONNECTIVITY dimension"
            )
        if (
            self.origin is not None
            and self.dimension is not EvidenceDimension.NATURAL_OR_ARTIFICIAL_ORIGIN
        ):
            raise ValueError(
                "origin is only valid on the NATURAL_OR_ARTIFICIAL_ORIGIN dimension"
            )
        if self.claim_class is ClaimClass.COMPUTED and not (
            self.method and self.method_version
        ):
            raise ValueError("a COMPUTED claim must name its method and version")
        decided = {AdjudicationStatus.ACCEPTED, AdjudicationStatus.REJECTED}
        if self.adjudication in decided:
            _require_text(self.adjudicated_by, "adjudicated_by")
            _require_text(self.adjudicated_utc, "adjudicated_utc")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be later than valid_to")


@dataclass(frozen=True)
class DerivedGeometry(_Record):
    """A shape computed from observations.  Never an observation itself."""

    geometry_id: str
    observation_ids: tuple[str, ...]
    method: str
    method_version: str
    geometry: Mapping[str, Any]
    geometry_logical_sha256: str
    horizontal_uncertainty_m: float | None = None
    modeled: bool = True

    def __post_init__(self) -> None:
        if not is_geometry_id(self.geometry_id):
            raise ValueError("geometry_id must be an APGEO identifier")
        _require_tuple(self.observation_ids, "observation_ids")
        if not self.observation_ids:
            raise ValueError(
                "a derived geometry must cite the observations it came from"
            )
        _require_text(self.method, "method")
        _require_text(self.method_version, "method_version")
        validate_geometry(self.geometry)
        if self.geometry_logical_sha256 != canonical_json_sha256(
            _jsonable(self.geometry)
        ):
            raise ValueError("geometry_logical_sha256 does not match the geometry")


@dataclass(frozen=True)
class Feature(_Record):
    """The registry's statement about one physical feature."""

    feature_id: str
    namespace: Namespace
    feature_class: str
    status: RegistryStatus = RegistryStatus.PROVISIONAL_DISCOVERY
    observation_ids: tuple[str, ...] = ()
    assertions: tuple[EvidenceAssertion, ...] = ()
    geometry_id: str | None = None
    provisional_labels: tuple[str, ...] = ()
    raw_names: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    created_utc: str | None = None
    updated_utc: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        require_registry_namespace(self.namespace)
        if not is_feature_id(self.feature_id, self.namespace):
            raise ValueError("feature_id does not belong to this registry namespace")
        allowed = {member.value for member in FEATURE_CLASSES[self.namespace]}
        if self.feature_class not in allowed:
            raise ValueError(
                f"{self.feature_class!r} is not a feature class of {self.namespace.value}"
            )
        for name in (
            "observation_ids",
            "assertions",
            "provisional_labels",
            "raw_names",
            "supersedes",
        ):
            _require_tuple(getattr(self, name), name)
        for obs in self.observation_ids:
            if not is_observation_id(obs, self.namespace):
                raise ValueError(
                    f"observation {obs!r} belongs to another registry namespace"
                )
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("duplicate observation reference")
        if self.geometry_id is not None and not is_geometry_id(self.geometry_id):
            raise ValueError("geometry_id must be an APGEO identifier")
        for prior in self.supersedes:
            if not is_feature_id(prior, self.namespace):
                raise ValueError(
                    "supersedes must reference features of the same registry"
                )
        if self.feature_id in self.supersedes:
            raise ValueError("a feature cannot supersede itself")


@dataclass(frozen=True)
class Relationship(_Record):
    """A typed, evidenced link between two records, possibly across registries."""

    relationship_id: str
    relationship_type: RelationshipType
    source: TypedRef
    target: TypedRef
    claim_class: ClaimClass
    tier: EvidenceTier
    basis: tuple[str, ...]
    statement: str
    source_ids: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()
    connectivity_kind: ConnectivityKind | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    adjudication: AdjudicationStatus = AdjudicationStatus.UNREVIEWED
    adjudicated_by: str | None = None
    adjudicated_utc: str | None = None
    contradicts: tuple[str, ...] = ()
    distance_m: float | None = None

    def __post_init__(self) -> None:
        if not is_relationship_id(self.relationship_id):
            raise ValueError("relationship_id must be an APREL identifier")
        _require_text(self.statement, "statement")
        for name in ("basis", "source_ids", "observation_ids", "contradicts"):
            _require_tuple(getattr(self, name), name)
        if self.source == self.target:
            raise ValueError("a relationship needs two distinct ends")
        if any(not is_source_id(s) for s in self.source_ids):
            raise ValueError("source_ids must be APSRC identifiers")
        if any(not is_relationship_id(r) for r in self.contradicts):
            raise ValueError("contradicts must reference relationship ids")
        if self.distance_m is not None and (
            not math.isfinite(self.distance_m) or self.distance_m < 0
        ):
            raise ValueError("distance_m must be a finite non-negative number")
        decided = {AdjudicationStatus.ACCEPTED, AdjudicationStatus.REJECTED}
        if self.adjudication in decided:
            _require_text(self.adjudicated_by, "adjudicated_by")
            _require_text(self.adjudicated_utc, "adjudicated_utc")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be later than valid_to")
