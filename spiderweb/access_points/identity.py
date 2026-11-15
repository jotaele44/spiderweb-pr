"""Identity adjudication between observations and physical features.

Identity is never proven by a name, a count, a category, a normalised
coordinate or a distance.  Those bases produce *candidate* correspondences
only.  An identity binding needs an authoritative basis and an independent
reviewer.

Correspondence cardinality is preserved exactly as found.  One observation
that matches several features stays one observation with several candidate
links; it is not copied, and records are never multiplied by a join.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from federation.spatial_core import IDENTITY_DEFAULT, geodesic_distance_m

from .namespaces import NamespaceCollisionError, TypedRef
from .vocabulary import DISCOVERY_ONLY_BASES, AdjudicationStatus, Cardinality

IDENTITY_BINDING = "IDENTITY_BINDING"

# Bases that can carry identity.  Each still needs independent acceptance.
AUTHORITATIVE_IDENTITY_BASES: frozenset[str] = frozenset(
    {
        "authoritative_stable_identifier",
        "same_source_record",
        "surveyed_same_monument",
        "field_verified_same_feature",
        "documented_same_structure",
    }
)


@dataclass(frozen=True, slots=True)
class Correspondence:
    """A proposed or adjudicated link "these two records are the same thing"."""

    left: TypedRef
    right: TypedRef
    basis: tuple[str, ...]
    statement: str
    distance_m: float | None = None
    adjudication: AdjudicationStatus = AdjudicationStatus.UNREVIEWED
    adjudicated_by: str | None = None

    def __post_init__(self) -> None:
        if self.left.namespace is not self.right.namespace:
            raise NamespaceCollisionError(
                f"{self.left} and {self.right} are in different namespaces; identity across "
                "namespaces is expressed as a typed relationship, not a correspondence"
            )
        if self.left == self.right:
            raise ValueError("a record trivially corresponds to itself")
        if not self.basis:
            raise ValueError("a correspondence must state its basis")
        if not self.statement.strip():
            raise ValueError("statement is required")


def identity_semantics(correspondence: Correspondence, *, producer_identity: str) -> str:
    """``IDENTITY_BINDING`` only with authoritative basis and independent acceptance."""

    bases = {b.strip().lower() for b in correspondence.basis}
    if not bases & AUTHORITATIVE_IDENTITY_BASES:
        return IDENTITY_DEFAULT
    if correspondence.adjudication is not AdjudicationStatus.ACCEPTED:
        return IDENTITY_DEFAULT
    reviewer = (correspondence.adjudicated_by or "").strip()
    if not reviewer or reviewer == producer_identity.strip():
        return IDENTITY_DEFAULT
    return IDENTITY_BINDING


def is_discovery_only(correspondence: Correspondence) -> bool:
    bases = {b.strip().lower() for b in correspondence.basis}
    return bool(bases) and bases <= DISCOVERY_ONLY_BASES


@dataclass(frozen=True, slots=True)
class CorrespondenceGroup:
    """One connected group of corresponding records and its cardinality."""

    left: tuple[TypedRef, ...]
    right: tuple[TypedRef, ...]
    cardinality: Cardinality
    correspondences: tuple[Correspondence, ...]


def group_correspondences(
    left_universe: Sequence[TypedRef],
    right_universe: Sequence[TypedRef],
    correspondences: Iterable[Correspondence],
) -> list[CorrespondenceGroup]:
    """Partition two record sets into correspondence groups.

    Every record of both universes appears in exactly one group, so counts
    close: unmatched records form ``0:1`` groups rather than vanishing.
    A group holding a correspondence that is ``UNRESOLVED`` or ``CONTRADICTED``
    is reported as ``UNRESOLVED`` whatever its shape.
    """

    links = list(correspondences)
    left_set, right_set = set(left_universe), set(right_universe)
    if len(left_set) != len(left_universe) or len(right_set) != len(right_universe):
        raise ValueError("duplicate record in a universe")
    if left_set & right_set:
        raise ValueError("a record cannot be on both sides of a correspondence")
    parent: dict[TypedRef, TypedRef] = {ref: ref for ref in list(left_universe) + list(right_universe)}

    def find(node: TypedRef) -> TypedRef:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for link in links:
        a, b = link.left, link.right
        if a in right_set and b in left_set:
            a, b = b, a
        if a not in left_set or b not in right_set:
            raise ValueError(f"correspondence {a} ~ {b} references a record outside the universes")
        parent[find(a)] = find(b)

    members: dict[TypedRef, list[TypedRef]] = {}
    for ref in parent:
        members.setdefault(find(ref), []).append(ref)
    groups: list[CorrespondenceGroup] = []
    for root in sorted(members, key=str):
        refs = members[root]
        lefts = tuple(sorted((r for r in refs if r in left_set), key=str))
        rights = tuple(sorted((r for r in refs if r in right_set), key=str))
        involved = tuple(
            l for l in links if find(l.left) == root
        )
        unsettled = any(
            l.adjudication in {AdjudicationStatus.UNRESOLVED, AdjudicationStatus.CONTRADICTED}
            for l in involved
        )
        if unsettled:
            cardinality = Cardinality.UNRESOLVED
        elif not lefts or not rights:
            cardinality = Cardinality.ZERO_TO_ONE
        elif len(lefts) == 1 and len(rights) == 1:
            cardinality = Cardinality.ONE_TO_ONE
        elif len(lefts) == 1:
            cardinality = Cardinality.ONE_TO_MANY
        elif len(rights) == 1:
            cardinality = Cardinality.MANY_TO_ONE
        else:
            cardinality = Cardinality.MANY_TO_MANY
        groups.append(CorrespondenceGroup(lefts, rights, cardinality, involved))
    return groups


def counts_close(
    left_universe: Sequence[TypedRef],
    right_universe: Sequence[TypedRef],
    groups: Sequence[CorrespondenceGroup],
) -> bool:
    """True if grouping neither lost nor multiplied a record."""

    return sum(len(g.left) for g in groups) == len(left_universe) and sum(
        len(g.right) for g in groups
    ) == len(right_universe)


def propose_by_proximity(
    left: Sequence[tuple[TypedRef, tuple[float, float]]],
    right: Sequence[tuple[TypedRef, tuple[float, float]]],
    *,
    threshold_m: float,
) -> list[Correspondence]:
    """Candidate correspondences for every pair within ``threshold_m``.

    All pairs are returned -- nothing is forced to one-to-one -- and every one
    is ``CANDIDATE_NOT_IDENTITY`` by construction.
    """

    if threshold_m < 0:
        raise ValueError("threshold_m must be non-negative")
    proposals: list[Correspondence] = []
    for left_ref, (llon, llat) in left:
        for right_ref, (rlon, rlat) in right:
            distance = geodesic_distance_m(llon, llat, rlon, rlat)
            if distance <= threshold_m:
                proposals.append(
                    Correspondence(
                        left=left_ref,
                        right=right_ref,
                        basis=("proximity_only",),
                        statement=f"{distance:.1f} m apart; {IDENTITY_DEFAULT}",
                        distance_m=distance,
                    )
                )
    proposals.sort(key=lambda c: (str(c.left), str(c.right)))
    return proposals
