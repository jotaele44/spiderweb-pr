from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gebco.marine_evidence import (
    CoverageState,
    DepthTransform,
    EvidenceState,
    MarineObservation,
    ProductStage,
    SensorType,
    VerticalCompatibilityError,
    VerticalReference,
    classify_feature_evidence,
    compare_depths,
    independent_root_ids,
    source_lineage_roots,
    validate_lineage,
)


WGS84_MLLW = VerticalReference(
    horizontal_crs="EPSG:4326",
    vertical_crs=None,
    vertical_datum="MLLW",
    tidal_datum="MLLW",
    depth_positive="down",
)

WGS84_NAVD88 = VerticalReference(
    horizontal_crs="EPSG:4326",
    vertical_crs="EPSG:5703",
    vertical_datum="NAVD88",
    tidal_datum=None,
    depth_positive="up",
)


def observation(
    observation_id: str,
    *,
    sensor: SensorType = SensorType.MULTIBEAM_ECHOSOUNDER,
    stage: ProductStage = ProductStage.RAW_OBSERVATION,
    root: str | None = "survey-a",
    coverage: CoverageState = CoverageState.DIRECTLY_OBSERVED,
    value: float | None = -10.0,
    uncertainty: float | None = 0.2,
    vertical: VerticalReference = WGS84_MLLW,
    parents: tuple[str, ...] = (),
) -> MarineObservation:
    return MarineObservation(
        observation_id=observation_id,
        sensor=sensor,
        stage=stage,
        root_survey_id=root,
        vertical_reference=vertical,
        coverage=coverage,
        value_m=value,
        uncertainty_m=uncertainty,
        observed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        parent_ids=parents,
    )


def test_zero_depth_is_valid_data_not_no_data() -> None:
    zero = observation("zero", value=0.0)
    missing = observation("missing", value=None, coverage=CoverageState.NULL_EMPTY)

    assert zero.has_value is True
    assert missing.has_value is False


def test_exact_vertical_reference_allows_depth_difference() -> None:
    a = observation("a", value=10.0, uncertainty=0.3)
    b = observation("b", value=12.0, uncertainty=0.4)

    result = compare_depths(a, b)

    assert result.delta_b_minus_a_m == pytest.approx(2.0)
    assert result.combined_uncertainty_m == pytest.approx(0.5)
    assert result.transform_authority is None


def test_unknown_or_mismatched_vertical_reference_fails_closed() -> None:
    a = observation("a", value=10.0)
    b = observation("b", value=-12.0, vertical=WGS84_NAVD88)

    with pytest.raises(VerticalCompatibilityError):
        compare_depths(a, b)


def test_explicit_certified_transform_allows_depth_difference() -> None:
    a = observation("a", value=10.0)
    b = observation("b", value=-12.0, vertical=WGS84_NAVD88)
    transform = DepthTransform(
        source=WGS84_NAVD88,
        target=WGS84_MLLW,
        scale=-1.0,
        offset_m=0.5,
        authority="NOAA VDatum test binding",
    )

    result = compare_depths(a, b, transforms=(transform,))

    assert result.delta_b_minus_a_m == pytest.approx(2.5)
    assert result.transform_authority == "NOAA VDatum test binding"


def test_derivatives_from_same_root_do_not_manufacture_independence() -> None:
    raw = observation("raw", root="survey-a")
    grid = observation(
        "grid",
        sensor=SensorType.DERIVED_BATHYMETRIC_GRID,
        stage=ProductStage.GRID,
        root="survey-a",
        coverage=CoverageState.INTERPOLATED,
        parents=("raw",),
    )
    chart = observation(
        "chart",
        sensor=SensorType.NAUTICAL_CHART,
        stage=ProductStage.DERIVED_PRODUCT,
        root="survey-a",
        coverage=CoverageState.GENERALIZED,
        parents=("grid",),
    )

    assert independent_root_ids((raw, grid, chart)) == frozenset({"survey-a"})
    assert classify_feature_evidence((raw, grid, chart)) is EvidenceState.SINGLE_SENSOR_SUPPORTED


def test_two_direct_sensor_families_and_two_roots_are_multisensor() -> None:
    multibeam = observation("mb", root="survey-a")
    lidar = observation(
        "lidar",
        sensor=SensorType.BATHYMETRIC_LIDAR,
        root="survey-b",
        value=10.1,
    )

    assert classify_feature_evidence((multibeam, lidar)) is EvidenceState.MULTISENSOR_CONFIRMED


def test_two_roots_with_one_sensor_family_are_not_multisensor() -> None:
    a = observation("a", root="survey-a")
    b = observation("b", root="survey-b")

    assert classify_feature_evidence((a, b)) is EvidenceState.DIRECT_SENSOR_CONFIRMED


def test_interpolated_surface_is_never_direct_observation() -> None:
    grid = observation(
        "grid",
        sensor=SensorType.DERIVED_BATHYMETRIC_GRID,
        stage=ProductStage.GRID,
        coverage=CoverageState.INTERPOLATED,
    )

    assert grid.is_direct_sensor_observation is False
    assert classify_feature_evidence((grid,)) is EvidenceState.INTERPOLATED_ONLY


def test_visualization_only_is_not_sensor_confirmation() -> None:
    view = observation(
        "view",
        sensor=SensorType.VISUALIZATION,
        stage=ProductStage.VISUALIZATION,
        coverage=CoverageState.GENERALIZED,
    )

    assert classify_feature_evidence((view,)) is EvidenceState.VISUALIZATION_ONLY


def test_tile_or_stitch_flag_demotes_derived_only_feature_to_artifact_candidate() -> None:
    view = observation(
        "view",
        sensor=SensorType.DERIVED_BATHYMETRIC_GRID,
        stage=ProductStage.DERIVED_PRODUCT,
        coverage=CoverageState.INTERPOLATED,
    )

    assert classify_feature_evidence(
        (view,), artifact_flags=("TILE_SEAM_COINCIDENCE",)
    ) is EvidenceState.ARTIFACT_CANDIDATE


def test_artifact_flag_does_not_override_direct_multisensor_evidence() -> None:
    multibeam = observation("mb", root="survey-a")
    lidar = observation(
        "lidar",
        sensor=SensorType.BATHYMETRIC_LIDAR,
        root="survey-b",
    )

    assert classify_feature_evidence(
        (multibeam, lidar), artifact_flags=("HILLSHADE_DIRECTIONALITY",)
    ) is EvidenceState.MULTISENSOR_CONFIRMED


def test_null_empty_observations_are_no_sensor_coverage() -> None:
    empty = observation(
        "empty",
        value=None,
        root=None,
        coverage=CoverageState.NULL_EMPTY,
        stage=ProductStage.GRID,
    )

    assert classify_feature_evidence((empty,)) is EvidenceState.NO_SENSOR_COVERAGE


def test_lineage_rejects_missing_parent() -> None:
    child = observation("child", parents=("missing",))

    with pytest.raises(ValueError, match="unknown lineage parent"):
        validate_lineage({"child": child})


def test_lineage_rejects_cycle() -> None:
    a = observation("a", parents=("b",))
    b = observation("b", parents=("a",))

    with pytest.raises(ValueError, match="lineage cycle"):
        validate_lineage({"a": a, "b": b})


def test_source_lineage_roots_resolve_raw_ancestor() -> None:
    raw = observation("raw", parents=())
    grid = observation(
        "grid",
        stage=ProductStage.GRID,
        coverage=CoverageState.INTERPOLATED,
        parents=("raw",),
    )
    view = observation(
        "view",
        stage=ProductStage.VISUALIZATION,
        sensor=SensorType.VISUALIZATION,
        coverage=CoverageState.GENERALIZED,
        parents=("grid",),
    )
    records = {item.observation_id: item for item in (raw, grid, view)}

    assert source_lineage_roots("view", records) == frozenset({"raw"})
