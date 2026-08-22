"""Puerto Rico archipelago geography capability.

This module provides the canonical *contract* for archipelagic geography.
It deliberately keeps source manifestations, canonical identities, geometries,
and operational classifications separate. Discovery is not identity proof.

The capability is source-agnostic: authoritative GNIS/NOAA/Census/PR source
snapshots are ingested elsewhere and normalized into the dataclasses below.
Certification remains OPEN until the current named and geometry denominators
close with zero unresolved current identity residue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


class IdentityState(str, Enum):
    RESOLVED_1_1 = "1:1"
    RESOLVED_1_N = "1:N"
    RESOLVED_N_1 = "N:1"
    RESOLVED_N_N = "N:N"
    SOURCE_ONLY_0_1 = "0:1"
    UNRESOLVED = "UNRESOLVED"


class SpatialState(str, Enum):
    FULLY_WITHIN = "FULLY_WITHIN"
    PARTIAL = "PARTIAL"
    TOUCH_ONLY = "TOUCH_ONLY"
    OUTSIDE = "OUTSIDE"
    NULL_EMPTY = "NULL_EMPTY"
    UNRESOLVED = "UNRESOLVED"


class GeometryRepresentation(str, Enum):
    """Native or derived geometric representation of one manifestation.

    Representation is deliberately independent of canonical feature type. A
    named rock/cay may have a source-native POINT and independent shoreline
    LINE evidence without a defensible POLYGON. Polygon absence is therefore
    not equivalent to geometry absence.
    """

    POINT = "POINT"
    LINE = "LINE"
    POLYGON = "POLYGON"
    MULTIPOINT = "MULTIPOINT"
    MULTILINE = "MULTILINE"
    MULTIPOLYGON = "MULTIPOLYGON"
    RASTER_DERIVED = "RASTER_DERIVED"
    UNRESOLVED = "UNRESOLVED"


class GeometryOrigin(str, Enum):
    SOURCE_NATIVE = "SOURCE_NATIVE"
    DERIVED = "DERIVED"
    UNRESOLVED = "UNRESOLVED"


class ArchipelagicPosition(str, Enum):
    ON_MAIN_ISLAND = "ON_MAIN_ISLAND"
    ON_OUTLYING_ISLAND = "ON_OUTLYING_ISLAND"
    ON_CAY = "ON_CAY"
    ON_ISLET = "ON_ISLET"
    ON_OTHER_EMERGENT_FEATURE = "ON_OTHER_EMERGENT_FEATURE"
    BETWEEN_INSULAR_FEATURES = "BETWEEN_INSULAR_FEATURES"
    NEAR_INSULAR_FEATURE = "NEAR_INSULAR_FEATURE"
    OFFSHORE_WITHIN_ARCHIPELAGIC_ENVELOPE = "OFFSHORE_WITHIN_ARCHIPELAGIC_ENVELOPE"
    OFFSHORE_OUTSIDE_ARCHIPELAGIC_ENVELOPE = "OFFSHORE_OUTSIDE_ARCHIPELAGIC_ENVELOPE"
    UNRESOLVED = "UNRESOLVED"


class CertificationState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"
    PROVISIONAL = "PROVISIONAL"
    AUDIT_ONLY = "AUDIT_ONLY"
    NONCANONICAL = "NONCANONICAL"
    CANDIDATE_NOT_IDENTITY = "CANDIDATE_NOT_IDENTITY"
    UNRESOLVED = "UNRESOLVED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class SourceManifestation:
    manifestation_id: str
    source_id: str
    source_name_raw: str
    feature_type_raw: str
    geometry_manifestation_id: Optional[str] = None
    stable_source_feature_id: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    historical: bool = False
    snapshot_sha256: Optional[str] = None
    retrieval_utc: Optional[str] = None


@dataclass(frozen=True)
class GeometryManifestation:
    """One explicitly sourced or derived geometry manifestation.

    A geometry manifestation is not a canonical feature identity. Candidate
    bindings may be many-to-many and remain unresolved until separately
    adjudicated.
    """

    geometry_manifestation_id: str
    source_id: str
    representation: GeometryRepresentation
    origin: GeometryOrigin
    source_geometry_type_raw: str
    source_feature_id: Optional[str] = None
    candidate_canonical_feature_ids: tuple[str, ...] = field(default_factory=tuple)
    snapshot_sha256: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


@dataclass(frozen=True)
class CanonicalInsularFeature:
    canonical_feature_id: str
    canonical_name: str
    canonical_feature_type: str
    manifestation_ids: tuple[str, ...]
    identity_state: IdentityState
    geometry_state: SpatialState = SpatialState.UNRESOLVED
    municipality: Optional[str] = None
    active: bool = True
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DenominatorDiff:
    intersection: frozenset[str]
    a_only: frozenset[str]
    b_only: frozenset[str]
    union: frozenset[str]
    symmetric_difference: frozenset[str]


def compare_denominators(a: Iterable[str], b: Iterable[str]) -> DenominatorDiff:
    """Compute the full A/B denominator comparison without asserting identity.

    Inputs must already be stable identity keys for the compared scope. Raw or
    normalized names are not acceptable identity keys.
    """
    a_set = frozenset(a)
    b_set = frozenset(b)
    return DenominatorDiff(
        intersection=a_set & b_set,
        a_only=a_set - b_set,
        b_only=b_set - a_set,
        union=a_set | b_set,
        symmetric_difference=a_set ^ b_set,
    )


def current_denominator_certification(
    *,
    named_total: int,
    geometry_total: int,
    resolved_current: int,
    unresolved_current: int,
    duplicate_unresolved: int,
    arithmetic_closed: bool,
    snapshots_frozen: bool,
) -> CertificationState:
    """Fail closed on the current archipelago denominator.

    PASS means only that the supplied bounded denominator satisfies these
    explicit gates; it does not claim universal historical or public-source
    exhaustion. geometry_total counts accepted geometry manifestations across
    permitted representations; it must never be interpreted as polygon_total.
    """
    counts = (named_total, geometry_total, resolved_current, unresolved_current, duplicate_unresolved)
    if any(v < 0 for v in counts):
        return CertificationState.FAIL
    if unresolved_current or duplicate_unresolved:
        return CertificationState.OPEN
    if not arithmetic_closed or not snapshots_frozen:
        return CertificationState.OPEN
    if named_total == 0 or geometry_total == 0 or resolved_current == 0:
        return CertificationState.OPEN
    return CertificationState.PASS


def assert_manifestation_conservation(
    *, source_manifestations: int, resolved: int, unresolved: int
) -> None:
    """Assert SOURCE_MANIFESTATIONS = RESOLVED + UNRESOLVED."""
    if min(source_manifestations, resolved, unresolved) < 0:
        raise ValueError("counts must be non-negative")
    if source_manifestations != resolved + unresolved:
        raise ValueError(
            "manifestation arithmetic does not close: "
            f"{source_manifestations} != {resolved} + {unresolved}"
        )
