import pytest

from federation.surface_analysis import IdentityState, MeasurementClass, ResolutionSummary, SpatialAnalysisResult, SpatialState


def result(**changes):
    values = dict(analysis_id="a1", query_id="q1", subject_type="flight_track", subject_id="t1", subject_manifestation_id="tm1", geometry_role="TRACK_POSITION_UNCERTAINTY", input_geometry_hash="a" * 64, target_domain="OCEAN_DEPTH", spatial_state=SpatialState.PARTIAL, identity_state=IdentityState.CANDIDATE_NOT_IDENTITY, target_candidate_id="ridge-1", source_manifestation_ids=("gebco-2023-pr",), measurement_classes=(MeasurementClass.INTERPOLATED,), resolution_summary=ResolutionSummary(463.0, 463.0, 463.0, 0.0, 1.0, 0.0), analysis_engine_version="surface/1.0", crs_operation="EPSG:4326->EPSG:32620", horizontal_source_crs="EPSG:4326", horizontal_computation_crs="EPSG:32620", vertical_datum="mean_sea_level_assumed", depth_sign_convention="positive_up", surface_depth_min_m=-800.0, surface_depth_max_m=-500.0, surface_depth_mean_m=-650.0)
    values.update(changes)
    return SpatialAnalysisResult(**values)


def test_artifact_hash_round_trip():
    artifact = result().as_artifact()
    assert SpatialAnalysisResult.verify_artifact(artifact)
    artifact["surface_depth_mean_m"] = -1
    assert not SpatialAnalysisResult.verify_artifact(artifact)


def test_nodata_cannot_become_zero_measurement():
    with pytest.raises(ValueError, match="NULL_EMPTY"):
        result(spatial_state=SpatialState.NULL_EMPTY, surface_depth_min_m=0.0, surface_depth_max_m=None, surface_depth_mean_m=None)


def test_candidate_never_promoted_to_identity():
    with pytest.raises(ValueError, match="CANDIDATE_NOT_IDENTITY"):
        result(identity_state=IdentityState.AUTHORITATIVE_BINDING)


def test_unknown_vertical_datum_blocks_depth():
    with pytest.raises(ValueError, match="vertical datum"):
        result(vertical_datum=None)


def test_resolution_fraction_and_order_gates():
    with pytest.raises(ValueError, match="exceed"):
        ResolutionSummary(10, 20, 10, 0.6, 0.5, 0.0)
    with pytest.raises(ValueError, match="best_m"):
        ResolutionSummary(30, 10, 20, 1, 0, 0)
