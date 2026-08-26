from spiderweb.spatial.archipelago_adjudication import (
    FootprintState,
    GeometryEvidenceSummary,
    adjudicate_footprint,
    footprint_certification,
)


def test_source_point_is_geometry_but_not_resolved_footprint():
    state = adjudicate_footprint(
        GeometryEvidenceSummary(
            stable_source_feature_id="GNIS:1613390",
            has_source_native_point=True,
        )
    )
    assert state == FootprintState.SOURCE_POINT_ONLY


def test_line_proximity_never_resolves_footprint():
    state = adjudicate_footprint(
        GeometryEvidenceSummary(
            stable_source_feature_id="GNIS:1613131",
            has_source_native_point=True,
            has_line_corroboration=True,
        )
    )
    assert state == FootprintState.LINE_CORROBORATED_CANDIDATE


def test_polygon_candidate_never_resolves_without_hard_binding():
    state = adjudicate_footprint(
        GeometryEvidenceSummary(
            stable_source_feature_id="GNIS:1609809",
            has_source_native_point=True,
            has_line_corroboration=True,
            has_polygon_candidate=True,
        )
    )
    assert state == FootprintState.POLYGON_CANDIDATE


def test_hard_binding_is_required_for_resolved_footprint():
    state = adjudicate_footprint(
        GeometryEvidenceSummary(
            stable_source_feature_id="GNIS:1609809",
            has_source_native_point=True,
            has_line_corroboration=True,
            has_polygon_candidate=True,
            hard_footprint_binding=True,
        )
    )
    assert state == FootprintState.FOOTPRINT_RESOLVED


def test_footprint_certification_fails_closed_on_candidate_residue():
    assert not footprint_certification(resolved=113, unresolved=0, candidate_only=35)
    assert footprint_certification(resolved=148, unresolved=0, candidate_only=0)
