"""Controlled vocabularies shared by both access-point registries.

Existing repository vocabularies are imported, not redefined:

* ``SpatialState``, ``EvidenceTier`` and ``CertificationState`` come from
  :mod:`spiderweb.subsurface.evidence`;
* sensor, product-stage and coverage vocabularies come from
  :mod:`gebco.marine_evidence`;
* the identity default ``CANDIDATE_NOT_IDENTITY`` and the federation relation
  verbs come from :mod:`federation.spatial_core` / ``spatial_relations``.

Everything defined here is new vocabulary that had no prior owner.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from federation.spatial_core import IDENTITY_DEFAULT
from federation.spatial_relations import RELATION_TYPES
from spiderweb.subsurface.evidence import CertificationState, EvidenceTier, SpatialState
from spiderweb.subsurface.svt_contract import CARDINALITIES, NON_PROMOTION_BASES

__all__ = [
    "AdjudicationStatus",
    "AssertionRung",
    "Cardinality",
    "CertificationState",
    "ClaimClass",
    "ConnectivityKind",
    "DISCOVERY_ONLY_BASES",
    "EvidenceDimension",
    "EvidenceTier",
    "FEDERATION_RELATION_VERB",
    "GeometryBasis",
    "IDENTITY_DEFAULT",
    "IdentityKind",
    "InlandFeatureClass",
    "MORPHOLOGY_ONLY_BASES",
    "OffshoreFeatureClass",
    "Origin",
    "ProvenanceState",
    "RELATIONSHIP_CONNECTIVITY_KIND",
    "RecordLayer",
    "RegistryStatus",
    "RelationshipType",
    "SpatialState",
    "VERIFIED_RELATIONSHIP_TYPES",
]


class ClaimClass(StrEnum):
    """How a statement was arrived at.  Every reported statement carries one."""

    FACT = "FACT"  # read directly from a registered primary source
    COMPUTED = "COMPUTED"  # deterministic output of a versioned method
    BINDING = "BINDING"  # an explicit, evidenced link between two records
    INFERENCE = "INFERENCE"  # reasoned from facts; could be wrong
    ASSUMPTION = "ASSUMPTION"  # taken as given without evidence
    HYPOTHESIS = "HYPOTHESIS"  # proposed for testing; not supported yet
    UNKNOWN = "UNKNOWN"


class EvidenceDimension(StrEnum):
    """Independent questions about a feature.  None answers another."""

    EXISTENCE = "EXISTENCE"
    MORPHOLOGY = "MORPHOLOGY"
    NATURAL_OR_ARTIFICIAL_ORIGIN = "NATURAL_OR_ARTIFICIAL_ORIGIN"
    PHYSICAL_OPENING = "PHYSICAL_OPENING"
    ACCESSIBILITY = "ACCESSIBILITY"
    FUNCTION = "FUNCTION"
    CONNECTIVITY = "CONNECTIVITY"
    TEMPORAL_VALIDITY = "TEMPORAL_VALIDITY"


class AssertionRung(IntEnum):
    """The strongest statement the evidence supports about one feature.

    A rung is always computed from the evidence dimensions; it is never stored
    as an input.  Each rung requires the one below it.
    """

    ANOMALY = 0  # something was noticed; nothing more
    FEATURE = 1  # a physical feature exists there
    OPENING = 2  # the feature has a physical opening
    PASSAGE = 3  # the opening can be entered
    CONNECTION = 4  # the passage reaches somewhere else


class RecordLayer(StrEnum):
    RAW = "RAW"  # exactly as the source published it
    NORMALIZED = "NORMALIZED"  # reprojected / unit-converted, losslessly traceable
    CANONICAL = "CANONICAL"  # the registry's adjudicated statement


class IdentityKind(StrEnum):
    SOURCE_MANIFESTATION = "SOURCE_MANIFESTATION"
    ORIGINAL_OBSERVATION = "ORIGINAL_OBSERVATION"
    PHYSICAL_FEATURE = "PHYSICAL_FEATURE"
    DERIVED_GEOMETRY = "DERIVED_GEOMETRY"
    RELATIONSHIP = "RELATIONSHIP"
    HISTORICAL_CONTINUITY = "HISTORICAL_CONTINUITY"


class Cardinality(StrEnum):
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_ONE = "N:1"
    MANY_TO_MANY = "N:N"
    ZERO_TO_ONE = "0:1"
    UNRESOLVED = "UNRESOLVED"


# Same six values as the repository's existing cardinality vocabulary.
assert {member.value for member in Cardinality} == set(CARDINALITIES)


class RegistryStatus(StrEnum):
    PROVISIONAL_DISCOVERY = (
        "PROVISIONAL_DISCOVERY"  # noticed; provenance not yet registered
    )
    CANDIDATE = "CANDIDATE"  # source-backed, not adjudicated
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"  # independently adjudicated
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class AdjudicationStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class ProvenanceState(StrEnum):
    """Whether the bytes behind a source are actually held and hashed."""

    REGISTERED = "REGISTERED"  # exact bytes frozen with SHA-256
    REFERENCED_ONLY = "REFERENCED_ONLY"  # a stable identifier/URL, bytes not held
    UNREGISTERED = "UNREGISTERED"  # described by an operator; nothing attached


class GeometryBasis(StrEnum):
    """Where a geometry came from.  Decides what it may be used for."""

    MEASURED = "MEASURED"  # surveyed coordinates from the source
    SOURCE_DIGITIZED = "SOURCE_DIGITIZED"  # digitised by the source publisher
    DERIVED_FROM_RASTER = "DERIVED_FROM_RASTER"  # delineated by a versioned method
    GEOREGISTERED_IMAGE = (
        "GEOREGISTERED_IMAGE"  # from an image with certified control points
    )
    LOCALITY_LABEL_ONLY = "LOCALITY_LABEL_ONLY"  # a place name; no coordinates exist
    NONE = "NONE"


class Origin(StrEnum):
    NATURAL = "NATURAL"
    ARTIFICIAL = "ARTIFICIAL"
    MODIFIED_NATURAL = "MODIFIED_NATURAL"
    UNDETERMINED = "UNDETERMINED"


class InlandFeatureClass(StrEnum):
    """Terrestrial / inland-subsurface classes.  Deliberately not collapsed."""

    CLOSED_DEPRESSION = "CLOSED_DEPRESSION"
    SINKHOLE = "SINKHOLE"
    SWALLOW_HOLE = "SWALLOW_HOLE"
    SPRING = "SPRING"
    CAVE_ENTRANCE = "CAVE_ENTRANCE"
    MINE_ADIT = "MINE_ADIT"
    MINE_SHAFT = "MINE_SHAFT"
    SURFACE_EXCAVATION = "SURFACE_EXCAVATION"
    TUNNEL_PORTAL = "TUNNEL_PORTAL"
    ENGINEERED_SHAFT = "ENGINEERED_SHAFT"
    CONDUIT_PORTAL = "CONDUIT_PORTAL"
    ENGINEERED_UNDERGROUND_STRUCTURE = "ENGINEERED_UNDERGROUND_STRUCTURE"
    UNCLASSIFIED_ANOMALY = "UNCLASSIFIED_ANOMALY"


class OffshoreFeatureClass(StrEnum):
    """Marine / submerged classes.  Deliberately not collapsed."""

    SEAFLOOR_DEPRESSION = "SEAFLOOR_DEPRESSION"
    BLUE_HOLE_CANDIDATE = "BLUE_HOLE_CANDIDATE"
    SUBMARINE_CAVE_ENTRANCE = "SUBMARINE_CAVE_ENTRANCE"
    SUBMARINE_SPRING = "SUBMARINE_SPRING"
    SUBMERGED_KARST_SURFACE = "SUBMERGED_KARST_SURFACE"
    ESCARPMENT = "ESCARPMENT"
    SHELF_EDGE_NOTCH = "SHELF_EDGE_NOTCH"
    SEAFLOOR_LINEAMENT = "SEAFLOOR_LINEAMENT"
    SUBMARINE_LANDSLIDE_SCAR = "SUBMARINE_LANDSLIDE_SCAR"
    ENGINEERED_OUTFALL = "ENGINEERED_OUTFALL"
    ENGINEERED_SEABED_STRUCTURE = "ENGINEERED_SEABED_STRUCTURE"
    UTILITY_LANDING = "UTILITY_LANDING"
    SURVEY_ARTIFACT = "SURVEY_ARTIFACT"
    UNCLASSIFIED_ANOMALY = "UNCLASSIFIED_ANOMALY"


class ConnectivityKind(StrEnum):
    """Four different things that are all loosely called "connected".

    Evidence for one is never evidence for another.
    """

    GEOLOGICAL_CONTINUITY = "GEOLOGICAL_CONTINUITY"
    HYDRAULIC_CONNECTION = "HYDRAULIC_CONNECTION"
    ENGINEERED_CONNECTIVITY = "ENGINEERED_CONNECTIVITY"
    HUMAN_ACCESSIBILITY = "HUMAN_ACCESSIBILITY"


class RelationshipType(StrEnum):
    SAME_VERIFIED_PHYSICAL_FEATURE = "SAME_VERIFIED_PHYSICAL_FEATURE"
    DOCUMENTED_ENGINEERED_CONNECTION = "DOCUMENTED_ENGINEERED_CONNECTION"
    MEASURED_HYDRAULIC_CONNECTION = "MEASURED_HYDRAULIC_CONNECTION"
    VERIFIED_GEOLOGICAL_CONTINUITY = "VERIFIED_GEOLOGICAL_CONTINUITY"
    SHARED_GEOLOGICAL_UNIT = "SHARED_GEOLOGICAL_UNIT"
    SPATIAL_ADJACENCY = "SPATIAL_ADJACENCY"
    HYPOTHESIZED_CONNECTION = "HYPOTHESIZED_CONNECTION"
    CONTRADICTORY_RELATIONSHIP = "CONTRADICTORY_RELATIONSHIP"
    UNRESOLVED_RELATIONSHIP = "UNRESOLVED_RELATIONSHIP"


# Relationship types that may, once adjudicated on direct evidence, be drawn as
# a verified physical link.  Everything else is context or conjecture.
VERIFIED_RELATIONSHIP_TYPES: frozenset[RelationshipType] = frozenset(
    {
        RelationshipType.SAME_VERIFIED_PHYSICAL_FEATURE,
        RelationshipType.DOCUMENTED_ENGINEERED_CONNECTION,
        RelationshipType.MEASURED_HYDRAULIC_CONNECTION,
        RelationshipType.VERIFIED_GEOLOGICAL_CONTINUITY,
    }
)

# The connectivity kind each verified relationship type establishes.  A type
# establishes exactly one kind and nothing about the others.
RELATIONSHIP_CONNECTIVITY_KIND: dict[RelationshipType, ConnectivityKind] = {
    RelationshipType.DOCUMENTED_ENGINEERED_CONNECTION: ConnectivityKind.ENGINEERED_CONNECTIVITY,
    RelationshipType.MEASURED_HYDRAULIC_CONNECTION: ConnectivityKind.HYDRAULIC_CONNECTION,
    RelationshipType.VERIFIED_GEOLOGICAL_CONTINUITY: ConnectivityKind.GEOLOGICAL_CONTINUITY,
}

# How each relationship type is expressed with the federation's existing
# relation verbs when exported.  No new verb is introduced.
FEDERATION_RELATION_VERB: dict[RelationshipType, str] = {
    RelationshipType.SAME_VERIFIED_PHYSICAL_FEATURE: "LOCATED_AT",
    RelationshipType.DOCUMENTED_ENGINEERED_CONNECTION: "CONNECTED_TO",
    RelationshipType.MEASURED_HYDRAULIC_CONNECTION: "CONNECTED_TO",
    RelationshipType.VERIFIED_GEOLOGICAL_CONTINUITY: "CONNECTED_TO",
    RelationshipType.SHARED_GEOLOGICAL_UNIT: "WITHIN",
    RelationshipType.SPATIAL_ADJACENCY: "WITHIN_DISTANCE",
    RelationshipType.HYPOTHESIZED_CONNECTION: "NEAREST_TO",
    RelationshipType.CONTRADICTORY_RELATIONSHIP: "NEAREST_TO",
    RelationshipType.UNRESOLVED_RELATIONSHIP: "NEAREST_TO",
}
assert set(FEDERATION_RELATION_VERB.values()) <= RELATION_TYPES

# Bases that can discover a candidate but never support or prove anything.
# This is the repository's existing non-promotion set
# (``spiderweb.subsurface.svt_contract.NON_PROMOTION_BASES``) extended with
# bases specific to access points; the shared set is imported, not copied.
DISCOVERY_ONLY_BASES: frozenset[str] = NON_PROMOTION_BASES | frozenset(
    {
        "equal_count",
        "normalized_coordinates",
        "graph_reachability",
        "contract_record",
        "funding_record",
        "screenshot_annotation",
    }
)

# Bases that describe shape.  Shape can support EXISTENCE and MORPHOLOGY; it
# cannot establish an opening, an origin, a function or a connection.
MORPHOLOGY_ONLY_BASES: frozenset[str] = frozenset(
    {
        "morphology",
        "depression_shape",
        "terrain_derivative",
        "bathymetric_anomaly",
        "discovery_score",
        "hillshade_interpretation",
        "acoustic_reflector",
        "backscatter_texture",
    }
)
