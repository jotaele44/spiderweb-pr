"""Canonical-equivalence candidate components for PR_ARCHIPELAGO_GEOGRAPHY.

Components group source manifestations connected by explicit candidate edges.
They do not collapse manifestations and do not, by themselves, establish a
canonical identity.  Every node remains addressable and every edge retains its
evidence class and contradiction state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from spiderweb.spatial.archipelago import IdentityState
from spiderweb.spatial.archipelago_denominator import GeometryCandidateEdge


class ComponentState(str, Enum):
    RETAINED = "RETAINED"
    EXCLUDED = "EXCLUDED"
    CANDIDATE = "CANDIDATE"
    UNRESOLVED = "UNRESOLVED"


class ComponentEvidenceState(str, Enum):
    HARD_EVIDENCE_PRESENT = "HARD_EVIDENCE_PRESENT"
    HEURISTIC_ONLY = "HEURISTIC_ONLY"
    CONTRADICTORY = "CONTRADICTORY"
    NO_EDGE = "NO_EDGE"


@dataclass(frozen=True)
class EquivalenceNode:
    manifestation_id: str
    source_id: str
    named_manifestation: bool = False
    stable_source_feature_id: str | None = None


@dataclass(frozen=True)
class ComponentEdge:
    left_id: str
    right_id: str
    candidate_edge: GeometryCandidateEdge
    contradictory_attributes: bool = False

    def __post_init__(self) -> None:
        if self.left_id == self.right_id:
            raise ValueError("self-edge is not a valid equivalence candidate")
        expected = {
            self.candidate_edge.geometry_manifestation_id,
            self.candidate_edge.target_manifestation_id,
        }
        if {self.left_id, self.right_id} != expected:
            raise ValueError("component edge endpoints must match candidate edge endpoints")


@dataclass(frozen=True)
class EquivalenceComponent:
    component_id: str
    node_ids: tuple[str, ...]
    edge_count: int
    evidence_state: ComponentEvidenceState
    candidate_cardinality: IdentityState | None
    state: ComponentState = ComponentState.CANDIDATE
    named_node_ids: tuple[str, ...] = field(default_factory=tuple)
    geometry_only_node_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_geometry_only(self) -> bool:
        return bool(self.geometry_only_node_ids) and not self.named_node_ids


@dataclass(frozen=True)
class ComponentPartition:
    components_total: int
    retained: int
    excluded: int
    candidate: int
    unresolved: int

    @property
    def explained_total(self) -> int:
        return self.retained + self.excluded + self.candidate + self.unresolved

    @property
    def residue(self) -> int:
        return self.components_total - self.explained_total

    @property
    def arithmetic_closed(self) -> bool:
        return self.residue == 0


def _candidate_cardinality(node_ids: set[str], edges: tuple[ComponentEdge, ...]) -> IdentityState | None:
    if not edges:
        return None
    degree: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        degree[edge.left_id].add(edge.right_id)
        degree[edge.right_id].add(edge.left_id)
    degrees = sorted(len(v) for v in degree.values())
    if len(node_ids) == 2 and degrees == [1, 1]:
        return IdentityState.RESOLVED_1_1
    if max(degrees) == 1:
        # Disconnected degree-one pairs cannot occur inside one connected
        # component; retain N:N semantics defensively if malformed input ever
        # reaches here.
        return IdentityState.RESOLVED_N_N
    hubs = [node for node, neighbours in degree.items() if len(neighbours) > 1]
    leaves = [node for node, neighbours in degree.items() if len(neighbours) == 1]
    if len(hubs) == 1 and len(leaves) == len(node_ids) - 1:
        # Orientation is not inferred from graph shape.  Without an explicitly
        # designated source/target side, 1:N versus N:1 remains N:N candidate
        # topology at the undirected component level.
        return IdentityState.RESOLVED_N_N
    return IdentityState.RESOLVED_N_N


def build_equivalence_components(
    nodes: Iterable[EquivalenceNode],
    edges: Iterable[ComponentEdge],
) -> tuple[EquivalenceComponent, ...]:
    """Build connected candidate components without collapsing source nodes.

    Unknown edge endpoints and duplicate manifestation IDs fail closed. Exact
    geometry or other hard evidence makes a component eligible for
    adjudication only; contradictions dominate the component evidence state.
    """
    node_rows = tuple(nodes)
    edge_rows = tuple(edges)
    node_by_id = {node.manifestation_id: node for node in node_rows}
    if len(node_by_id) != len(node_rows):
        raise ValueError("duplicate manifestation_id in equivalence nodes")

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_by_id}
    edges_by_node: dict[str, list[ComponentEdge]] = {node_id: [] for node_id in node_by_id}
    for edge in edge_rows:
        if edge.left_id not in node_by_id or edge.right_id not in node_by_id:
            raise ValueError("equivalence edge references unknown manifestation")
        adjacency[edge.left_id].add(edge.right_id)
        adjacency[edge.right_id].add(edge.left_id)
        edges_by_node[edge.left_id].append(edge)
        edges_by_node[edge.right_id].append(edge)

    components: list[EquivalenceComponent] = []
    seen: set[str] = set()
    for seed in sorted(node_by_id):
        if seed in seen:
            continue
        stack = [seed]
        member_ids: set[str] = set()
        component_edges: dict[tuple[str, str], ComponentEdge] = {}
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            member_ids.add(current)
            for edge in edges_by_node[current]:
                key = tuple(sorted((edge.left_id, edge.right_id)))
                component_edges[key] = edge
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    stack.append(neighbour)

        edge_tuple = tuple(component_edges.values())
        contradictory = any(edge.contradictory_attributes for edge in edge_tuple)
        hard = any(edge.candidate_edge.has_hard_identity_evidence for edge in edge_tuple)
        if contradictory:
            evidence_state = ComponentEvidenceState.CONTRADICTORY
        elif hard:
            evidence_state = ComponentEvidenceState.HARD_EVIDENCE_PRESENT
        elif edge_tuple:
            evidence_state = ComponentEvidenceState.HEURISTIC_ONLY
        else:
            evidence_state = ComponentEvidenceState.NO_EDGE

        named = tuple(sorted(node_id for node_id in member_ids if node_by_id[node_id].named_manifestation))
        geometry_only = tuple(sorted(member_ids - set(named)))
        components.append(
            EquivalenceComponent(
                component_id="COMP:" + min(member_ids),
                node_ids=tuple(sorted(member_ids)),
                edge_count=len(edge_tuple),
                evidence_state=evidence_state,
                candidate_cardinality=_candidate_cardinality(member_ids, edge_tuple),
                state=ComponentState.CANDIDATE,
                named_node_ids=named,
                geometry_only_node_ids=geometry_only,
            )
        )
    return tuple(components)


def partition_components(components: Iterable[EquivalenceComponent]) -> ComponentPartition:
    rows = tuple(components)
    ids = [row.component_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate component_id")
    counts = {state: 0 for state in ComponentState}
    for row in rows:
        counts[row.state] += 1
    result = ComponentPartition(
        components_total=len(rows),
        retained=counts[ComponentState.RETAINED],
        excluded=counts[ComponentState.EXCLUDED],
        candidate=counts[ComponentState.CANDIDATE],
        unresolved=counts[ComponentState.UNRESOLVED],
    )
    if not result.arithmetic_closed:
        raise ValueError("component arithmetic does not close")
    return result


def assert_zero_canonical_component_residue(components: Iterable[EquivalenceComponent]) -> None:
    """Certification gate: candidate/unresolved components must both be zero."""
    partition = partition_components(components)
    if partition.candidate or partition.unresolved:
        raise ValueError(
            "canonical component residue remains: "
            f"candidate={partition.candidate}, unresolved={partition.unresolved}"
        )
