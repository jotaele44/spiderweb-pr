"""Typed relationships between access-point records, and paths through them.

Spatial proximity discovers a possible relationship.  It is never identity and
never connectivity.

Four different things are loosely called a "connection" -- geological
continuity, hydraulic connection, engineered connectivity and human
accessibility.  A relationship establishes at most one of them, and a path is
verified only if every edge is individually verified *for the same kind*.  A
path containing a single hypothesised, unresolved or contradicted edge is not a
verified path, and is never rendered as one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Mapping, Sequence

from federation.spatial_core import (
    IDENTITY_DEFAULT,
    canonical_json_sha256,
    geodesic_distance_m,
)

from . import CONTRACT_VERSION
from .models import Relationship, SourceManifestation
from .namespaces import (
    REGISTRY_NAMESPACES,
    Namespace,
    NamespaceCollisionError,
    TypedRef,
    relationship_id,
)
from .vocabulary import (
    DISCOVERY_ONLY_BASES,
    FEDERATION_RELATION_VERB,
    RELATIONSHIP_CONNECTIVITY_KIND,
    VERIFIED_RELATIONSHIP_TYPES,
    AdjudicationStatus,
    ClaimClass,
    ConnectivityKind,
    EvidenceTier,
    ProvenanceState,
    RelationshipType,
)

LEDGER_SCHEMA = "access_point_relationships/1.0"

# Relationship types a legacy (non-registry) record may take part in.  A legacy
# label can be near something or conjectured to relate to it; it can never be
# declared the same physical feature or a verified connection.
_LEGACY_ALLOWED = frozenset(
    {
        RelationshipType.SPATIAL_ADJACENCY,
        RelationshipType.HYPOTHESIZED_CONNECTION,
        RelationshipType.CONTRADICTORY_RELATIONSHIP,
        RelationshipType.UNRESOLVED_RELATIONSHIP,
    }
)

_SPECULATIVE = frozenset(
    {ClaimClass.HYPOTHESIS, ClaimClass.ASSUMPTION, ClaimClass.UNKNOWN}
)


class RenderClass(StrEnum):
    """How a relationship may be drawn.  The GUI maps these to line styles."""

    VERIFIED = "verified"
    CONTEXT = "context"
    HYPOTHESIZED = "hypothesized"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class PathState(StrEnum):
    VERIFIED = "VERIFIED"
    HYPOTHETICAL = "HYPOTHETICAL"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"
    MIXED_KINDS = "MIXED_KINDS"
    NO_PATH = "NO_PATH"


def make_relationship(
    relationship_type: RelationshipType,
    source: TypedRef,
    target: TypedRef,
    *,
    claim_class: ClaimClass,
    tier: EvidenceTier,
    basis: tuple[str, ...],
    statement: str,
    source_ids: tuple[str, ...] = (),
    observation_ids: tuple[str, ...] = (),
    connectivity_kind: ConnectivityKind | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    adjudication: AdjudicationStatus = AdjudicationStatus.UNREVIEWED,
    adjudicated_by: str | None = None,
    adjudicated_utc: str | None = None,
    contradicts: tuple[str, ...] = (),
    distance_m: float | None = None,
) -> Relationship:
    """Build a relationship, enforcing what each type is allowed to mean."""

    legacy_end = (
        source.namespace not in REGISTRY_NAMESPACES
        or target.namespace not in REGISTRY_NAMESPACES
    )
    if legacy_end and relationship_type not in _LEGACY_ALLOWED:
        raise NamespaceCollisionError(
            f"{relationship_type.value} cannot involve a legacy record "
            f"({source.namespace.value} -> {target.namespace.value}); legacy labels are "
            "never merged with, or verified against, access-point features"
        )
    expected_kind = RELATIONSHIP_CONNECTIVITY_KIND.get(relationship_type)
    if expected_kind is not None:
        if connectivity_kind is None:
            connectivity_kind = expected_kind
        elif connectivity_kind is not expected_kind:
            raise ValueError(
                f"{relationship_type.value} establishes {expected_kind.value}, "
                f"not {connectivity_kind.value}"
            )
    elif relationship_type is RelationshipType.HYPOTHESIZED_CONNECTION:
        if connectivity_kind is None:
            raise ValueError(
                "a hypothesised connection must say which kind it hypothesises"
            )
    elif connectivity_kind is not None and relationship_type in {
        RelationshipType.SAME_VERIFIED_PHYSICAL_FEATURE,
        RelationshipType.SHARED_GEOLOGICAL_UNIT,
        RelationshipType.SPATIAL_ADJACENCY,
    }:
        raise ValueError(
            f"{relationship_type.value} is not a connection and carries no kind"
        )
    if (
        relationship_type is RelationshipType.CONTRADICTORY_RELATIONSHIP
        and not contradicts
    ):
        raise ValueError("a contradictory relationship must name what it contradicts")
    return Relationship(
        relationship_id=relationship_id(
            relationship_type.value,
            source,
            target,
            None if connectivity_kind is None else connectivity_kind.value,
        ),
        relationship_type=relationship_type,
        source=source,
        target=target,
        claim_class=claim_class,
        tier=tier,
        basis=basis,
        statement=statement,
        source_ids=source_ids,
        observation_ids=observation_ids,
        connectivity_kind=connectivity_kind,
        valid_from=valid_from,
        valid_to=valid_to,
        adjudication=adjudication,
        adjudicated_by=adjudicated_by,
        adjudicated_utc=adjudicated_utc,
        contradicts=contradicts,
        distance_m=distance_m,
    )


def spatial_adjacency(
    source: TypedRef,
    source_lon_lat: tuple[float, float],
    target: TypedRef,
    target_lon_lat: tuple[float, float],
    *,
    threshold_m: float,
) -> Relationship | None:
    """Discover that two records are near each other.  Nothing more."""

    if threshold_m < 0:
        raise ValueError("threshold_m must be non-negative")
    distance = geodesic_distance_m(*source_lon_lat, *target_lon_lat)
    if distance > threshold_m:
        return None
    return make_relationship(
        RelationshipType.SPATIAL_ADJACENCY,
        source,
        target,
        claim_class=ClaimClass.COMPUTED,
        tier=EvidenceTier.CANDIDATE,
        basis=("proximity_only",),
        statement=(
            f"{distance:.1f} m apart (WGS84 geodesic, threshold {threshold_m:.1f} m); "
            f"{IDENTITY_DEFAULT}"
        ),
        distance_m=distance,
    )


def effective_tier(
    relationship: Relationship, sources: Mapping[str, SourceManifestation]
) -> EvidenceTier:
    """What a relationship's evidence is worth.  Never above what was asserted."""

    tier = relationship.tier
    if tier in {EvidenceTier.UNRESOLVED, EvidenceTier.CONTRADICTED}:
        return tier

    def cap(ceiling: EvidenceTier) -> None:
        nonlocal tier
        if tier > ceiling:
            tier = ceiling

    bases = {b.strip().lower() for b in relationship.basis}
    if not bases or bases & DISCOVERY_ONLY_BASES:
        cap(EvidenceTier.CANDIDATE)
    if relationship.claim_class in _SPECULATIVE:
        cap(EvidenceTier.CANDIDATE)
    elif relationship.claim_class is ClaimClass.INFERENCE:
        cap(EvidenceTier.SUPPORTING)
    if relationship.relationship_type not in VERIFIED_RELATIONSHIP_TYPES:
        cap(EvidenceTier.SUPPORTING)
    if relationship.relationship_type in {
        RelationshipType.SPATIAL_ADJACENCY,
        RelationshipType.HYPOTHESIZED_CONNECTION,
        RelationshipType.UNRESOLVED_RELATIONSHIP,
    }:
        cap(EvidenceTier.CANDIDATE)
    cited = [sources[s] for s in relationship.source_ids if s in sources]
    if len(cited) != len(relationship.source_ids):
        cited = []
    if not any(s.provenance_state is ProvenanceState.REGISTERED for s in cited):
        cap(EvidenceTier.SUPPORTING)
    if not any(s.provenance_state is not ProvenanceState.UNREGISTERED for s in cited):
        cap(EvidenceTier.CANDIDATE)
    return tier


class RelationshipLedger:
    """All relationships, including those that cross the two registries."""

    def __init__(self, *, producer_identity: str) -> None:
        if not producer_identity or not producer_identity.strip():
            raise ValueError("producer_identity is required")
        self.producer_identity = producer_identity.strip()
        self._relationships: dict[str, Relationship] = {}
        self._sources: dict[str, SourceManifestation] = {}

    @property
    def relationships(self) -> Mapping[str, Relationship]:
        return dict(self._relationships)

    @property
    def sources(self) -> Mapping[str, SourceManifestation]:
        return dict(self._sources)

    def add_source(self, source: SourceManifestation) -> None:
        existing = self._sources.get(source.source_id)
        if (
            existing is not None
            and existing.logical_sha256() != source.logical_sha256()
        ):
            raise ValueError(
                f"source {source.source_id} already exists with different content"
            )
        self._sources[source.source_id] = source

    def add(self, relationship: Relationship) -> bool:
        unknown = [s for s in relationship.source_ids if s not in self._sources]
        if unknown:
            raise ValueError(f"relationship cites unknown sources: {unknown}")
        missing = [r for r in relationship.contradicts if r not in self._relationships]
        if missing:
            raise ValueError(
                f"relationship contradicts unknown relationships: {missing}"
            )
        existing = self._relationships.get(relationship.relationship_id)
        if existing is None:
            self._relationships[relationship.relationship_id] = relationship
            return True
        if existing.logical_sha256() != relationship.logical_sha256():
            raise ValueError(
                f"relationship {relationship.relationship_id} already exists with different "
                "content; record a revision or a contradiction instead"
            )
        return False

    def revise(self, relationship: Relationship) -> Relationship:
        if relationship.relationship_id not in self._relationships:
            raise KeyError(relationship.relationship_id)
        self._relationships[relationship.relationship_id] = relationship
        return relationship

    def contradicted_ids(self) -> frozenset[str]:
        hit: set[str] = set()
        for relationship in self._relationships.values():
            if (
                relationship.relationship_type
                is RelationshipType.CONTRADICTORY_RELATIONSHIP
            ):
                hit.update(relationship.contradicts)
        return frozenset(hit)

    def is_verified(self, relationship: Relationship) -> bool:
        """A relationship that may be drawn and reported as physically established."""

        if relationship.relationship_type not in VERIFIED_RELATIONSHIP_TYPES:
            return False
        if relationship.relationship_id in self.contradicted_ids():
            return False
        if effective_tier(relationship, self._sources) is not EvidenceTier.DIRECT:
            return False
        if relationship.adjudication is not AdjudicationStatus.ACCEPTED:
            return False
        reviewer = (relationship.adjudicated_by or "").strip()
        return bool(reviewer) and reviewer != self.producer_identity

    def render_class(self, relationship: Relationship) -> RenderClass:
        if (
            relationship.relationship_type
            is RelationshipType.CONTRADICTORY_RELATIONSHIP
            or relationship.relationship_id in self.contradicted_ids()
            or relationship.tier is EvidenceTier.CONTRADICTED
        ):
            return RenderClass.CONTRADICTED
        if self.is_verified(relationship):
            return RenderClass.VERIFIED
        if relationship.relationship_type is RelationshipType.UNRESOLVED_RELATIONSHIP:
            return RenderClass.UNRESOLVED
        if relationship.relationship_type in {
            RelationshipType.SPATIAL_ADJACENCY,
            RelationshipType.SHARED_GEOLOGICAL_UNIT,
        }:
            return RenderClass.CONTEXT
        return RenderClass.HYPOTHESIZED

    def touching(self, ref: TypedRef) -> list[Relationship]:
        return sorted(
            (r for r in self._relationships.values() if ref in (r.source, r.target)),
            key=lambda r: r.relationship_id,
        )

    # -- paths -----------------------------------------------------------

    def assess_path(self, edges: Sequence[Relationship]) -> "PathAssessment":
        if not edges:
            return PathAssessment(PathState.NO_PATH, None, (), ())
        classes = [self.render_class(edge) for edge in edges]
        ids = tuple(edge.relationship_id for edge in edges)
        weak = tuple(
            edge.relationship_id
            for edge, cls in zip(edges, classes)
            if cls is not RenderClass.VERIFIED
        )
        if RenderClass.CONTRADICTED in classes:
            return PathAssessment(PathState.CONTRADICTED, None, ids, weak)
        if RenderClass.UNRESOLVED in classes:
            return PathAssessment(PathState.UNRESOLVED, None, ids, weak)
        if any(cls is not RenderClass.VERIFIED for cls in classes):
            return PathAssessment(PathState.HYPOTHETICAL, None, ids, weak)
        kinds = {
            edge.connectivity_kind
            for edge in edges
            if edge.relationship_type
            is not RelationshipType.SAME_VERIFIED_PHYSICAL_FEATURE
        }
        if len(kinds) > 1:
            # Every edge is verified, but for different things.  Water reaching
            # a place and a person reaching it are not one connection.
            return PathAssessment(PathState.MIXED_KINDS, None, ids, ())
        kind = next(iter(kinds)) if kinds else None
        return PathAssessment(PathState.VERIFIED, kind, ids, ())

    def paths(
        self, start: TypedRef, goal: TypedRef, *, max_hops: int = 6
    ) -> list["PathAssessment"]:
        """All simple paths up to ``max_hops``, each with its own assessment."""

        if max_hops < 1:
            raise ValueError("max_hops must be at least 1")
        adjacency: dict[TypedRef, list[tuple[TypedRef, Relationship]]] = {}
        for relationship in sorted(
            self._relationships.values(), key=lambda r: r.relationship_id
        ):
            if (
                relationship.relationship_type
                is RelationshipType.CONTRADICTORY_RELATIONSHIP
            ):
                continue
            adjacency.setdefault(relationship.source, []).append(
                (relationship.target, relationship)
            )
            adjacency.setdefault(relationship.target, []).append(
                (relationship.source, relationship)
            )
        found: list[PathAssessment] = []
        queue: deque[
            tuple[TypedRef, tuple[TypedRef, ...], tuple[Relationship, ...]]
        ] = deque([(start, (start,), ())])
        while queue:
            node, visited, edges = queue.popleft()
            if node == goal and edges:
                found.append(self.assess_path(edges))
                continue
            if len(edges) >= max_hops:
                continue
            for neighbour, relationship in adjacency.get(node, []):
                if neighbour in visited:
                    continue
                queue.append(
                    (neighbour, visited + (neighbour,), edges + (relationship,))
                )
        return found

    def best_path_state(
        self, start: TypedRef, goal: TypedRef, *, max_hops: int = 6
    ) -> PathState:
        states = [p.state for p in self.paths(start, goal, max_hops=max_hops)]
        if not states:
            return PathState.NO_PATH
        for preferred in (
            PathState.VERIFIED,
            PathState.MIXED_KINDS,
            PathState.HYPOTHETICAL,
            PathState.UNRESOLVED,
            PathState.CONTRADICTED,
        ):
            if preferred in states:
                return preferred
        return PathState.NO_PATH

    # -- export ----------------------------------------------------------

    def federation_rows(self) -> list[dict[str, Any]]:
        """Relationships expressed with the federation's existing relation verbs."""

        rows = []
        for relationship in sorted(
            self._relationships.values(), key=lambda r: r.relationship_id
        ):
            rows.append(
                {
                    "relationship_id": relationship.relationship_id,
                    "relation_type": FEDERATION_RELATION_VERB[
                        relationship.relationship_type
                    ],
                    "access_point_relationship_type": relationship.relationship_type.value,
                    "source_feature_id": str(relationship.source),
                    "target_feature_id": str(relationship.target),
                    "identity_semantics": (
                        "IDENTITY_BINDING"
                        if relationship.relationship_type
                        is RelationshipType.SAME_VERIFIED_PHYSICAL_FEATURE
                        and self.is_verified(relationship)
                        else IDENTITY_DEFAULT
                    ),
                    "render_class": self.render_class(relationship).value,
                    "evidence_tier": effective_tier(relationship, self._sources).name,
                    "claim_class": relationship.claim_class.value,
                    "distance_m": relationship.distance_m,
                }
            )
        return rows

    def to_document(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": LEDGER_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "producer_identity": self.producer_identity,
            "sources": [self._sources[k].to_dict() for k in sorted(self._sources)],
            "relationships": [
                self._relationships[k].to_dict() for k in sorted(self._relationships)
            ],
            "counts": {
                "relationships": len(self._relationships),
                "sources": len(self._sources),
            },
        }
        body["content_sha256"] = canonical_json_sha256(body)
        return body


@dataclass(frozen=True, slots=True)
class PathAssessment:
    state: PathState
    connectivity_kind: ConnectivityKind | None
    relationship_ids: tuple[str, ...]
    unverified_relationship_ids: tuple[str, ...]

    @property
    def may_render_as_verified(self) -> bool:
        return self.state is PathState.VERIFIED


def accept(relationship: Relationship, *, reviewer: str, utc: str) -> Relationship:
    """Return a copy recording an adjudication decision."""

    if not reviewer or not reviewer.strip():
        raise ValueError("a named reviewer is required")
    return replace(
        relationship,
        adjudication=AdjudicationStatus.ACCEPTED,
        adjudicated_by=reviewer.strip(),
        adjudicated_utc=utc,
    )


def relationship_from_dict(data: Mapping[str, Any]) -> Relationship:
    def ref(value: Mapping[str, Any]) -> TypedRef:
        return TypedRef(Namespace(value["namespace"]), value["identifier"])

    kind = data.get("connectivity_kind")
    return Relationship(
        relationship_id=data["relationship_id"],
        relationship_type=RelationshipType(data["relationship_type"]),
        source=ref(data["source"]),
        target=ref(data["target"]),
        claim_class=ClaimClass(data["claim_class"]),
        tier=EvidenceTier[data["tier"]],
        basis=tuple(data.get("basis") or ()),
        statement=data["statement"],
        source_ids=tuple(data.get("source_ids") or ()),
        observation_ids=tuple(data.get("observation_ids") or ()),
        connectivity_kind=None if kind is None else ConnectivityKind(kind),
        valid_from=data.get("valid_from"),
        valid_to=data.get("valid_to"),
        adjudication=AdjudicationStatus(
            data.get("adjudication", AdjudicationStatus.UNREVIEWED.value)
        ),
        adjudicated_by=data.get("adjudicated_by"),
        adjudicated_utc=data.get("adjudicated_utc"),
        contradicts=tuple(data.get("contradicts") or ()),
        distance_m=data.get("distance_m"),
    )


def ledger_from_document(document: Mapping[str, Any]) -> RelationshipLedger:
    from .registry import RegistryIntegrityError, source_from_dict

    if document.get("schema") != LEDGER_SCHEMA:
        raise RegistryIntegrityError(
            f"unsupported ledger schema: {document.get('schema')!r}"
        )
    body = {k: v for k, v in document.items() if k != "content_sha256"}
    if document.get("content_sha256") != canonical_json_sha256(body):
        raise RegistryIntegrityError("relationship ledger hash mismatch")
    ledger = RelationshipLedger(producer_identity=document["producer_identity"])
    try:
        for item in document.get("sources", []):
            ledger.add_source(source_from_dict(item))
        pending = [
            relationship_from_dict(item) for item in document.get("relationships", [])
        ]
        while pending:
            ready = [
                r
                for r in pending
                if all(c in ledger._relationships for c in r.contradicts)
            ]
            if not ready:
                raise RegistryIntegrityError(
                    "contradiction links are cyclic or dangling"
                )
            for relationship in ready:
                ledger.add(relationship)
            pending = [
                r for r in pending if r.relationship_id not in ledger._relationships
            ]
    except RegistryIntegrityError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise RegistryIntegrityError(f"relationship ledger is invalid: {exc}") from exc
    if document.get("counts", {}).get("relationships") != len(ledger._relationships):
        raise RegistryIntegrityError("relationship ledger counts do not close")
    return ledger
