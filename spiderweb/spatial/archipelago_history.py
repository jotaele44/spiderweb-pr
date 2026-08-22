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


@dataclass(frozen=True)
class HistoricalManifestationNode:
    manifestation_id: str
    source_id: str
    valid_time: str | None = None


@dataclass(frozen=True)
class TemporalEquivalenceComponent:
    component_id: str
    historical_manifestation_ids: tuple[str, ...]
    current_candidate_ids: tuple[str, ...]
    relation_states: tuple[TemporalRelation, ...]
    valid_times: tuple[str, ...]
    edge_count: int

    @property
    def may_promote_current_identity(self) -> bool:
        return False


def temporal_relation_counts(edges: Iterable[HistoricalRelationEdge]) -> dict[TemporalRelation, int]:
    counts = {relation: 0 for relation in TemporalRelation}
    for edge in edges:
        counts[edge.relation] += 1
    return counts


def build_temporal_components(
    nodes: Iterable[HistoricalManifestationNode],
    edges: Iterable[HistoricalRelationEdge],
) -> tuple[TemporalEquivalenceComponent, ...]:
    """Build B-only temporal components while preserving all source nodes.

    Current candidate IDs are terminal labels in this graph, not A nodes that
    may be mutated or certified here. Historical edges may join historical
    manifestations when they share a current candidate, but no relation state
    is inferred beyond the states explicitly carried by the source edges.
    """
    node_rows = tuple(nodes)
    edge_rows = tuple(edges)
    node_by_id = {node.manifestation_id: node for node in node_rows}
    if len(node_by_id) != len(node_rows):
        raise ValueError("duplicate historical manifestation_id")
    for edge in edge_rows:
        if edge.historical_manifestation_id not in node_by_id:
            raise ValueError("temporal edge references unknown historical manifestation")

    # Historical nodes are connected only when explicit edges point to the same
    # non-null current candidate. This preserves source manifestations while
    # exposing candidate continuity/split/merge topology for later adjudication.
    by_current: dict[str, list[HistoricalRelationEdge]] = {}
    isolated_edges: list[HistoricalRelationEdge] = []
    for edge in edge_rows:
        if edge.current_candidate_id is None:
            isolated_edges.append(edge)
        else:
            by_current.setdefault(edge.current_candidate_id, []).append(edge)

    components: list[TemporalEquivalenceComponent] = []
    used_hist: set[str] = set()
    for current_id in sorted(by_current):
        group = by_current[current_id]
        hist_ids = tuple(sorted({edge.historical_manifestation_id for edge in group}))
        used_hist.update(hist_ids)
        relations = tuple(sorted({edge.relation for edge in group}, key=lambda x: x.value))
        times = tuple(sorted({node_by_id[h].valid_time for h in hist_ids if node_by_id[h].valid_time is not None}))
        components.append(
            TemporalEquivalenceComponent(
                component_id=f"TEMP:{current_id}",
                historical_manifestation_ids=hist_ids,
                current_candidate_ids=(current_id,),
                relation_states=relations,
                valid_times=times,
                edge_count=len(group),
            )
        )

    for edge in isolated_edges:
        hid = edge.historical_manifestation_id
        used_hist.add(hid)
        node = node_by_id[hid]
        components.append(
            TemporalEquivalenceComponent(
                component_id=f"TEMP:{hid}",
                historical_manifestation_ids=(hid,),
                current_candidate_ids=(),
                relation_states=(edge.relation,),
                valid_times=(() if node.valid_time is None else (node.valid_time,)),
                edge_count=1,
            )
        )

    # Historical source manifestations without any relation edge remain
    # explicit UNRESOLVED singleton components rather than disappearing.
    for hid in sorted(set(node_by_id) - used_hist):
        node = node_by_id[hid]
        components.append(
            TemporalEquivalenceComponent(
                component_id=f"TEMP:{hid}",
                historical_manifestation_ids=(hid,),
                current_candidate_ids=(),
                relation_states=(TemporalRelation.UNRESOLVED,),
                valid_times=(() if node.valid_time is None else (node.valid_time,)),
                edge_count=0,
            )
        )
    return tuple(sorted(components, key=lambda c: c.component_id))


def assert_no_historical_backfill(edges: Iterable[HistoricalRelationEdge]) -> None:
    """Regression assertion that B contains no direct A-promotion mechanism."""
    for edge in edges:
        if edge.may_promote_current_identity:
            raise ValueError("historical edge attempted to promote current identity")


def assert_components_do_not_backfill(components: Iterable[TemporalEquivalenceComponent]) -> None:
    for component in components:
        if component.may_promote_current_identity:
            raise ValueError("historical component attempted to promote current identity")
