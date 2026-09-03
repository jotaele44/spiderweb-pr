from federation.spatial_relations import nearest, within_distance

A={"feature_id":"a","geometry":{"type":"Point","coordinates":[-66.1,18.45]}}
B={"feature_id":"b","geometry":{"type":"Point","coordinates":[-66.11,18.45]}}
C={"feature_id":"c","geometry":{"type":"Point","coordinates":[-67.0,18.0]}}

def test_within_distance_is_identity_safe():
    rel=within_distance(A,B,2000)
    assert rel is not None
    assert rel.relation_type=="WITHIN_DISTANCE"
    assert rel.identity_semantics=="CANDIDATE_NOT_IDENTITY"
    assert rel.distance_m is not None and rel.distance_m < 2000

def test_outside_threshold_returns_none():
    assert within_distance(A,C,1000) is None

def test_nearest_is_deterministic():
    rel=nearest(A,[C,B])
    assert rel is not None and rel.target_feature_id=="b"
