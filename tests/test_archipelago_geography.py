from spiderweb.spatial.archipelago import (
    CertificationState,
    GeometryManifestation,
    GeometryOrigin,
    GeometryRepresentation,
    compare_denominators,
    current_denominator_certification,
    assert_manifestation_conservation,
)


def _closed_current(**overrides):
    kwargs = {
        "named_total": 100,
        "geometry_total": 105,
        "resolved_current": 110,
        "unresolved_current": 0,
        "duplicate_unresolved": 0,
        "unresolved_geometry": 0,
        "candidate_only_geometry": 0,
        "arithmetic_closed": True,
        "snapshots_frozen": True,
        "identity_denominator_closed": True,
        "geometry_denominator_closed": True,
        "source_evidence_durable": True,
    }
    kwargs.update(overrides)
    return current_denominator_certification(**kwargs)


def test_denominator_diff_closes():
    diff = compare_denominators({"a", "b", "c"}, {"b", "c", "d"})
    assert diff.intersection == frozenset({"b", "c"})
    assert diff.a_only == frozenset({"a"})
    assert diff.b_only == frozenset({"d"})
    assert diff.union == frozenset({"a", "b", "c", "d"})
    assert diff.symmetric_difference == frozenset({"a", "d"})


def test_geometry_manifestation_can_be_source_native_point():
    geom = GeometryManifestation(
        geometry_manifestation_id="GNIS:1612633:POINT",
        source_id="GNIS",
        representation=GeometryRepresentation.POINT,
        origin=GeometryOrigin.SOURCE_NATIVE,
        source_geometry_type_raw="Point",
        source_feature_id="1612633",
    )
    assert geom.representation == GeometryRepresentation.POINT
    assert geom.origin == GeometryOrigin.SOURCE_NATIVE


def test_derived_line_or_polygon_is_not_identity_by_construction():
    geom = GeometryManifestation(
        geometry_manifestation_id="NOAA:CUSP:N15W070:derived-1",
        source_id="NOAA_CUSP",
        representation=GeometryRepresentation.POLYGON,
        origin=GeometryOrigin.DERIVED,
        source_geometry_type_raw="Polyline polygonization",
        candidate_canonical_feature_ids=("PR-CANDIDATE-1", "PR-CANDIDATE-2"),
    )
    assert geom.origin == GeometryOrigin.DERIVED
    assert len(geom.candidate_canonical_feature_ids) == 2


def test_current_denominator_pass_requires_all_closure_gates():
    assert _closed_current() == CertificationState.PASS


def test_current_denominator_open_on_unresolved_identity():
    assert _closed_current(unresolved_current=1) == CertificationState.OPEN


def test_current_denominator_open_on_unresolved_geometry():
    assert _closed_current(unresolved_geometry=1) == CertificationState.OPEN


def test_current_denominator_open_on_candidate_only_geometry():
    assert _closed_current(candidate_only_geometry=1) == CertificationState.OPEN


def test_current_denominator_open_when_identity_denominator_not_closed():
    assert _closed_current(identity_denominator_closed=False) == CertificationState.OPEN


def test_current_denominator_open_when_geometry_denominator_not_closed():
    assert _closed_current(geometry_denominator_closed=False) == CertificationState.OPEN


def test_current_denominator_open_when_snapshots_not_frozen():
    assert _closed_current(snapshots_frozen=False) == CertificationState.OPEN


def test_current_denominator_open_when_source_evidence_not_durable():
    assert _closed_current(source_evidence_durable=False) == CertificationState.OPEN


def test_manifestation_arithmetic_gate():
    assert_manifestation_conservation(source_manifestations=10, resolved=8, unresolved=2)


def test_manifestation_arithmetic_gate_rejects_mismatch():
    try:
        assert_manifestation_conservation(source_manifestations=10, resolved=8, unresolved=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected arithmetic mismatch to fail closed")
