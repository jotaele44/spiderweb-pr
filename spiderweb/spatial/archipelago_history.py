"""Independent historical relation graph for PR_ARCHIPELAGO_GEOGRAPHY.

Historical evidence may characterize continuity, rename, split, merge, or
possible disappearance. It cannot by itself resolve the current A denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class TemporalRelation(str, Enum):
    CONTINUITY = "CONTINUITY"
    RENAMED = "RENAMED"
    SPLIT = "SPLIT"
    MERGED = "MERGED"
    DISAPPEARED = "DISAPPEARED"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    UNRESOLVED = "UNRESOLVED"


class TemporalEvidenceKind(str, Enum):
    STABLE_SOURCE_ID = "STABLE_SOURCE_ID"
    AUTHORITATIVE_MAP_LABEL = "AUTHORITATIVE_MAP_LABEL"
    AUTHORITATIVE_GEOMETRY = "AUTHORITATIVE_GEOMETRY"
    EXPLICIT_LINEAGE_STATEMENT = "EXPLICIT_LINEAGE_STATEMENT"
    NAME_ONLY = "NAME_ONLY"
    PROXIMITY_ONLY = "PROXIMITY_ONLY"


@dataclass(frozen=True)
class HistoricalRelationEdge:
    historical_manifestation_id: str
    current_candidate_id: str | None
    relation: TemporalRelation
    evidence: tuple[TemporalEvidenceKind, ...]
    valid_time: str | None = None
    note: str = ""

    @property
    def may_promote_current_identity(self) -> bool:
        """Always false: B cannot directly certify A."""
        return False


def temporal_relation_counts(edges: Iterable[HistoricalRelationEdge]) -> dict[TemporalRelation, int]:
    counts = {relation: 0 for relation in TemporalRelation}
    for edge in edges:
        counts[edge.relation] += 1
    return counts


def assert_no_historical_backfill(edges: Iterable[HistoricalRelationEdge]) -> None:
    """Regression assertion that B contains no direct A-promotion mechanism."""
    for edge in edges:
        if edge.may_promote_current_identity:
            raise ValueError("historical edge attempted to promote current identity")
