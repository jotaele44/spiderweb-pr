import pytest

from integration.htr_context import HTRContextError, import_htr_graph


def base_row():
    return {
        "candidate_id": "htr_seed",
        "source_observation_id": "toponym:calle_luchetti_villalba",
        "source_feature_type": "ROAD",
        "hydro_entity_id": "hydro-name-family:antonio_lucchetti",
        "state": "CONTEXT_SUPPORTED",
        "identity_state": "DISTINCT_ENTITIES",
        "downstream_semantics": "CONTEXT_ONLY_NOT_IDENTITY",
        "relation_type": "ORTHOGRAPHIC_VARIANT",
        "pair_binding_state": "UNBOUND",
    }


def test_unbound_name_match_stays_possible_epnym_not_identity():
    graph = import_htr_graph([base_row()])
    assert graph["invariants"]["identity_edge_count"] == 0
    assert graph["invariants"]["node_count"] == 2
    assert graph["edges"][0]["relationship_type"] == "POSSIBLE_EPONYM_OF"
    assert graph["edges"][0]["identity_claim"] is False
    assert all(n["identity_locked"] is True for n in graph["nodes"])


def test_bound_relation_remains_non_identity():
    r = base_row()
    r.update(
        state="ADJUDICATED",
        pair_binding_state="BOUND_RELATION_NOT_IDENTITY",
        relation_type="NAMED_AFTER",
    )
    edge = import_htr_graph([r])["edges"][0]
    assert edge["relationship_type"] == "NAMED_AFTER"
    assert edge["identity_claim"] is False


def test_discovery_only_and_same_as_are_rejected():
    r = base_row(); r["state"] = "CANDIDATE_NOT_IDENTITY"
    with pytest.raises(HTRContextError):
        import_htr_graph([r])
    r = base_row(); r["relation_type"] = "SAME_AS"
    with pytest.raises(HTRContextError):
        import_htr_graph([r])
