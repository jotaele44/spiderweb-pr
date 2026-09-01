import pytest

from spiderweb.spatial.archipelago import IdentityState
from spiderweb.spatial.archipelago_components import (
    ComponentEdge,
    ComponentEvidenceState,
    ComponentState,
    EquivalenceNode,
    assert_zero_canonical_component_residue,
    build_equivalence_components,
    partition_components,
)
from spiderweb.spatial.archipelago_denominator import (
    CandidateEvidenceKind,
    GeometryCandidateEdge,
)


def _edge(left, right, evidence, contradiction=False):
    candidate = GeometryCandidateEdge(
        geometry_manifestation_id=left,
        target_manifestation_id=right,
        evidence=tuple(evidence),
    )
    return ComponentEdge(left, right, candidate, contradictory_attributes=contradiction)


def test_exact_pair_remains_two_source_nodes_in_one_candidate_component():
    nodes = [EquivalenceNode("a", "NOAA"), EquivalenceNode("b", "NOAA")]
    comps = build_equivalence_components(
        nodes,
        [_edge("a", "b", [CandidateEvidenceKind.EXACT_SOURCE_GEOMETRY_KEY])],
    )
    assert len(comps) == 1
    assert comps[0].node_ids == ("a", "b")
    assert comps[0].candidate_cardinality == IdentityState.RESOLVED_1_1
    assert comps[0].state == ComponentState.CANDIDATE
    assert comps[0].evidence_state == ComponentEvidenceState.HARD_EVIDENCE_PRESENT


def test_contradiction_dominates_hard_geometry_evidence():
    nodes = [EquivalenceNode("a", "NOAA"), EquivalenceNode("b", "NOAA")]
    comps = build_equivalence_components(
        nodes,
        [_edge("a", "b", [CandidateEvidenceKind.EXACT_SOURCE_GEOMETRY_KEY], contradiction=True)],
    )
    assert comps[0].evidence_state == ComponentEvidenceState.CONTRADICTORY
    assert comps[0].state == ComponentState.CANDIDATE


def test_no_edge_geometry_node_is_geometry_only_component():
    comp = build_equivalence_components([EquivalenceNode("geom", "CUSP")], [])[0]
    assert comp.is_geometry_only
    assert comp.evidence_state == ComponentEvidenceState.NO_EDGE


def test_named_node_prevents_geometry_only_classification():
    comp = build_equivalence_components(
        [EquivalenceNode("sige:1", "SIGE", named_manifestation=True)], []
    )[0]
    assert not comp.is_geometry_only
    assert comp.named_node_ids == ("sige:1",)


def test_component_builder_rejects_unknown_edge_endpoint():
    with pytest.raises(ValueError, match="unknown manifestation"):
        build_equivalence_components(
            [EquivalenceNode("a", "NOAA")],
            [_edge("a", "missing", [CandidateEvidenceKind.PROXIMITY_ONLY])],
        )


def test_component_partition_closes_but_candidates_block_certification():
    comps = build_equivalence_components(
        [EquivalenceNode("a", "NOAA"), EquivalenceNode("b", "NOAA")],
        [_edge("a", "b", [CandidateEvidenceKind.EXACT_SOURCE_GEOMETRY_KEY])],
    )
    part = partition_components(comps)
    assert part.components_total == 1
    assert part.candidate == 1
    assert part.arithmetic_closed
    with pytest.raises(ValueError, match="canonical component residue"):
        assert_zero_canonical_component_residue(comps)


def test_transitive_component_does_not_imply_canonical_merge():
    nodes = [EquivalenceNode(x, "TEST") for x in ("a", "b", "c")]
    comps = build_equivalence_components(
        nodes,
        [
            _edge("a", "b", [CandidateEvidenceKind.EXACT_SOURCE_GEOMETRY_KEY]),
            _edge("b", "c", [CandidateEvidenceKind.EXPLICIT_PROVIDER_CROSSWALK]),
        ],
    )
    assert len(comps) == 1
    assert comps[0].node_ids == ("a", "b", "c")
    assert comps[0].state == ComponentState.CANDIDATE
    assert comps[0].candidate_cardinality == IdentityState.RESOLVED_N_N
