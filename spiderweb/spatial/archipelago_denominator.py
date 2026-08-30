"""Fail-closed geometry-manifestation denominator for PR_ARCHIPELAGO_GEOGRAPHY.

This module partitions *source geometry manifestations*, not canonical islands.
Every manifestation must occupy exactly one terminal ledger bucket:
RETAINED, EXCLUDED, CANDIDATE, or UNRESOLVED. Candidate edges preserve full
many-to-many cardinality and never promote identity from name, normalization,
proximity, count equality, nearest-neighbour, or geometry overlap alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from spiderweb.spatial.archipelago import GeometryManifestation, IdentityState


class GeometryLedgerState(str, Enum):
    RETAINED = "RETAINED"
    EXCLUDED = "EXCLUDED"
    CANDIDATE = "CANDIDATE"
    UNRESOLVED = "UNRESOLVED"


class CandidateEvidenceKind(str, Enum):
    """Evidence attached to a candidate edge.

    The HEURISTIC values below are deliberately representable because the
    evidence must be preserved, but none can independently authorize identity.
    """

    STABLE_SOURCE_ID = "STABLE_SOURCE_ID"
    EXPLICIT_PROVIDER_CROSSWALK = "EXPLICIT_PROVIDER_CROSSWALK"
    AUTHORITATIVE_LINEAGE = "AUTHORITATIVE_LINEAGE"
    EXACT_SOURCE_GEOMETRY_KEY = "EXACT_SOURCE_GEOMETRY_KEY"
    NAME_ONLY = "NAME_ONLY"
    NORMALIZED_NAME_ONLY = "NORMALIZED_NAME_ONLY"
    PROXIMITY_ONLY = "PROXIMITY_ONLY"
    NEAREST_ONLY = "NEAREST_ONLY"
    GEOMETRY_OVERLAP_ONLY = "GEOMETRY_OVERLAP_ONLY"
    COUNT_EQUALITY = "COUNT_EQUALITY"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"


HARD_IDENTITY_EVIDENCE = frozenset(
    {
        CandidateEvidenceKind.STABLE_SOURCE_ID,
        CandidateEvidenceKind.EXPLICIT_PROVIDER_CROSSWALK,
        CandidateEvidenceKind.AUTHORITATIVE_LINEAGE,
        CandidateEvidenceKind.EXACT_SOURCE_GEOMETRY_KEY,
    }
)


@dataclass(frozen=True)
class GeometryCandidateEdge:
    geometry_manifestation_id: str
    target_manifestation_id: str
    evidence: tuple[CandidateEvidenceKind, ...]
    note: str = ""

    @property
    def has_hard_identity_evidence(self) -> bool:
        return any(kind in HARD_IDENTITY_EVIDENCE for kind in self.evidence)


@dataclass(frozen=True)
class GeometryLedgerEntry:
    manifestation: GeometryManifestation
    state: GeometryLedgerState
    candidate_target_ids: tuple[str, ...] = field(default_factory=tuple)
    exclusion_reason: str | None = None
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        targets = tuple(dict.fromkeys(self.candidate_target_ids))
        object.__setattr__(self, "candidate_target_ids", targets)
        if self.state == GeometryLedgerState.CANDIDATE and not targets:
            raise ValueError("CANDIDATE entry must preserve a non-empty candidate set")
        if self.state != GeometryLedgerState.CANDIDATE and targets:
            raise ValueError("candidate_target_ids are allowed only for CANDIDATE entries")
        if self.state == GeometryLedgerState.EXCLUDED and not self.exclusion_reason:
            raise ValueError("EXCLUDED entry requires exclusion_reason")
        if self.state == GeometryLedgerState.UNRESOLVED and not self.unresolved_reason:
            raise ValueError("UNRESOLVED entry requires unresolved_reason")


@dataclass(frozen=True)
class GeometryPartition:
    source_total: int
    retained: int
    excluded: int
    candidate: int
    unresolved: int

    @property
    def explained_total(self) -> int:
        return self.retained + self.excluded + self.candidate + self.unresolved

    @property
    def residue(self) -> int:
        return self.source_total - self.explained_total

    @property
    def arithmetic_closed(self) -> bool:
        return self.residue == 0


def partition_geometry_ledger(entries: Iterable[GeometryLedgerEntry]) -> GeometryPartition:
    rows = tuple(entries)
    ids = [row.manifestation.geometry_manifestation_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate geometry_manifestation_id in denominator ledger")
    counts = {state: 0 for state in GeometryLedgerState}
    for row in rows:
        counts[row.state] += 1
    partition = GeometryPartition(
        source_total=len(rows),
        retained=counts[GeometryLedgerState.RETAINED],
        excluded=counts[GeometryLedgerState.EXCLUDED],
        candidate=counts[GeometryLedgerState.CANDIDATE],
        unresolved=counts[GeometryLedgerState.UNRESOLVED],
    )
    if not partition.arithmetic_closed:
        raise ValueError("geometry manifestation denominator arithmetic does not close")
    return partition


def candidate_cardinalities(edges: Iterable[GeometryCandidateEdge]) -> Mapping[str, IdentityState]:
    """Return candidate cardinality by geometry manifestation.

    Cardinality describes the candidate graph only; it is never a canonical
    identity conclusion. A left node with one target may still remain
    CANDIDATE_NOT_IDENTITY when its evidence is heuristic-only.
    """
    rows = tuple(edges)
    left_to_right: dict[str, set[str]] = {}
    right_to_left: dict[str, set[str]] = {}
    for edge in rows:
        left_to_right.setdefault(edge.geometry_manifestation_id, set()).add(edge.target_manifestation_id)
        right_to_left.setdefault(edge.target_manifestation_id, set()).add(edge.geometry_manifestation_id)

    result: dict[str, IdentityState] = {}
    for left, rights in left_to_right.items():
        if len(rights) > 1:
            if any(len(right_to_left[right]) > 1 for right in rights):
                result[left] = IdentityState.RESOLVED_N_N
            else:
                result[left] = IdentityState.RESOLVED_1_N
        else:
            right = next(iter(rights))
            result[left] = (
                IdentityState.RESOLVED_N_1
                if len(right_to_left[right]) > 1
                else IdentityState.RESOLVED_1_1
            )
    return result


def promotable_edges(edges: Iterable[GeometryCandidateEdge]) -> tuple[GeometryCandidateEdge, ...]:
    """Return only edges carrying at least one hard identity-evidence class.

    This is intentionally conservative. The presence of hard evidence makes an
    edge eligible for adjudication, not automatically canonical.
    """
    return tuple(edge for edge in edges if edge.has_hard_identity_evidence)


def assert_zero_unexplained_geometry_residue(entries: Iterable[GeometryLedgerEntry]) -> None:
    """Certification helper: fail unless every manifestation is terminally explained.

    CANDIDATE and UNRESOLVED are explained ledger states but still block
    canonical certification elsewhere. This function addresses *unexplained*
    arithmetic residue only.
    """
    partition = partition_geometry_ledger(entries)
    if partition.residue != 0:
        raise ValueError(f"unexplained geometry residue: {partition.residue}")
