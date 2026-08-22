from spiderweb.spatial.archipelago import (
    CertificationState,
    GeometryManifestation,
    GeometryOrigin,
    GeometryRepresentation,
    compare_denominators,
    current_denominator_certification,
    assert_manifestation_conservation,
)


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


def test_current_denominator_pass_requires_zero_residue_and_frozen_inputs():
    state = current_denominator_certification(
        named_total=100,
        geometry_total=105,
        resolved_current=110,
        unresolved_current=0,
        duplicate_unresolved=0,
        arithmetic_closed=True,
        snapshots_frozen=True,
    )
    assert state == CertificationState.PASS


def test_current_denominator_open_on_unresolved_identity():
    state = current_denominator_certification(
        named_total=100,
        geometry_total=105,
        resolved_current=109,
        unresolved_current=1,
        duplicate_unresolved=0,
        arithmetic_closed=True,
        snapshots_frozen=True,
    )
    assert state == CertificationState.OPEN


def test_current_denominator_open_when_snapshots_not_frozen():
    state = current_denominator_certification(
        named_total=100,
        geometry_total=105,
        resolved_current=110,
        unresolved_current=0,
        duplicate_unresolved=0,
        arithmetic_closed=True,
        snapshots_frozen=False,
    )
    assert state == CertificationState.OPEN


def test_manifestation_arithmetic_gate():
    assert_manifestation_conservation(source_manifestations=10, resolved=8, unresolved=2)


def test_manifestation_arithmetic_gate_rejects_mismatch():
    try:
        assert_manifestation_conservation(source_manifestations=10, resolved=8, unresolved=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected arithmetic mismatch to fail closed")
