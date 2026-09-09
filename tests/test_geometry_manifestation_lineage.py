"""Synthetic regression fixtures; no Puerto Rico empirical result is asserted."""
from dataclasses import replace
import pytest
from spiderweb.spatial.archipelago import GeometryManifestation as G, GeometryOrigin as O
from spiderweb.spatial.archipelago import GeometryRepresentation as R, GeometryDerivationState as D
from spiderweb.spatial.lineage_validation import validate_manifestation_dag


def node(k, parent=None, state=D.SOURCE_NATIVE):
    return G(k,"TEST_SYNTHETIC",R.POLYGON,O.SOURCE_NATIVE if state==D.SOURCE_NATIVE else O.DERIVED,"Polygon",parent_manifestation_id=parent,derivation_state=state)


def test_valid_lineage_preserves_noncertification():
    rows=[node("s"),node("f","s",D.CANONICALIZED_FULL),node("v","f",D.SIMPLIFIED),node("t","v",D.MVT)]
    result=validate_manifestation_dag(rows)
    assert (result.node_count,result.edge_count)==(4,3)
    assert result.canonical_identity_certified is False
    assert result.state=="PASS_STRUCTURAL_ONLY"


@pytest.mark.parametrize("rows,error",[
    ([],"EMPTY_LINEAGE"),
    ([node("s"),node("s")],"DUPLICATE"),
    ([node("f","absent",D.FULL)],"PARENT_NOT_FOUND"),
    ([node("f","f",D.FULL)],"SELF_EDGE"),
    ([node("a","b",D.FULL),node("b","a",D.FULL)],"LINEAGE_CYCLE"),
    ([node("s"),node("t","s",D.MVT),node("f","t",D.FULL)],"MVT_AUTHORITY_REVERSAL"),
    ([node("s"),node("f",None,D.FULL)],"MISSING_PARENT"),
    ([node("s","x")],"SOURCE_NATIVE_HAS_PARENT"),
    ([node("s",None,D.UNRESOLVED)],"UNRESOLVED_LINEAGE"),
    ([node("")],"EMPTY_MANIFESTATION_ID"),
    ([replace(node("s"),origin=O.DERIVED)],"ORIGIN_STATE_CONFLICT"),
])
def test_bad_lineage_rejected(rows,error):
    with pytest.raises(ValueError,match=error):validate_manifestation_dag(rows)


def test_long_graph_is_iterative():
    rows=[node("0")]+[node(str(i),str(i-1),D.FULL) for i in range(1,2000)]
    assert validate_manifestation_dag(rows).node_count==2000


def test_parent_deletion_rejected():
    with pytest.raises(ValueError,match="PARENT_NOT_FOUND"):
        validate_manifestation_dag([node("child","deleted",D.SIMPLIFIED)])


def test_legacy_constructs_but_does_not_pass_admission():
    legacy=G("legacy","TEST",R.POINT,O.SOURCE_NATIVE,"Point")
    assert legacy.parent_manifestation_id is None
    with pytest.raises(ValueError,match="UNRESOLVED_LINEAGE"):
        validate_manifestation_dag([legacy])
