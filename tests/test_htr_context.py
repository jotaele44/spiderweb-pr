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


def test_unbound_name_match_stays_possible_eponym_not_identity():
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
    r = base_row()
    r["state"] = "CANDIDATE_NOT_IDENTITY"
    with pytest.raises(HTRContextError):
        import_htr_graph([r])
    r = base_row()
    r["relation_type"] = "SAME_AS"
    with pytest.raises(HTRContextError):
        import_htr_graph([r])


@pytest.mark.parametrize("relation", [None, "", [], {}])
def test_relation_type_must_be_non_empty_string(relation):
    r = base_row()
    r["relation_type"] = relation
    with pytest.raises(HTRContextError, match="relation_type"):
        import_htr_graph([r])


def test_unknown_pair_binding_state_and_endpoint_collapse_are_rejected():
    r = base_row()
    r["pair_binding_state"] = "UNKNOWN"
    with pytest.raises(HTRContextError, match="pair_binding_state"):
        import_htr_graph([r])

    r = base_row()
    r["hydro_entity_id"] = r["source_observation_id"]
    with pytest.raises(HTRContextError, match="endpoints must remain distinct"):
        import_htr_graph([r])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_observation_id", "", "source_observation_id"),
        ("hydro_entity_id", None, "hydro_entity_id"),
        ("identity_state", "UNRESOLVED", "distinct entities"),
        ("downstream_semantics", "IDENTITY", "context-only contract"),
    ],
)
def test_graph_boundary_rejects_invalid_contract_fields(field, value, message):
    r = base_row()
    r[field] = value
    with pytest.raises(HTRContextError, match=message):
        import_htr_graph([r])


def test_unsupported_row_is_rejected():
    r = base_row()
    r["state"] = "UNSUPPORTED"
    r["identity_state"] = "UNRESOLVED"
    with pytest.raises(HTRContextError):
        import_htr_graph([r])
