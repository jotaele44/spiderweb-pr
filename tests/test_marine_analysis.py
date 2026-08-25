from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gebco.marine_evidence import (
    CoverageState,
    EvidenceState,
    GeomorphologyClass,
    MarineObservation,
    ProductStage,
    SensorType,
    VerticalReference,
)
from pipeline.marine_analysis import (
    MarineFeatureCandidate,
    assess_marine_feature,
    compare_temporal_observations,
    validate_observation_universe,
)


REFERENCE = VerticalReference(
    horizontal_crs="EPSG:4326",
    vertical_crs=None,
    vertical_datum="MLLW",
    tidal_datum="MLLW",
    depth_positive="down",
)

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def obs(
    observation_id: str,
    *,
    sensor: SensorType = SensorType.MULTIBEAM_ECHOSOUNDER,
    root: str = "survey-a",
    stage: ProductStage = ProductStage.RAW_OBSERVATION,
    coverage: CoverageState = CoverageState.DIRECTLY_OBSERVED,
    value: float | None = 10.0,
    when: datetime = NOW,
    parents: tuple[str, ...] = (),
) -> MarineObservation:
    return MarineObservation(
        observation_id=observation_id,
        sensor=sensor,
        stage=stage,
        root_survey_id=root,
        vertical_reference=REFERENCE,
        coverage=coverage,
        value_m=value,
        uncertainty_m=0.25,
        observed_at=when,
        parent_ids=parents,
    )


def test_pipeline_multisensor_feature_assessment() -> None:
    mb = obs("mb", root="noaa-mb-1")
    lidar = obs("lidar", sensor=SensorType.BATHYMETRIC_LIDAR, root="noaa-lidar-2")
    universe = validate_observation_universe((mb, lidar))
    candidate = MarineFeatureCandidate(
        feature_id="guayama-ridge-001",
        morphology=GeomorphologyClass.RIDGE,
        observation_ids=("mb", "lidar"),
    )

    result = assess_marine_feature(candidate, universe)

    assert result.evidence_state is EvidenceState.MULTISENSOR_CONFIRMED
    assert result.direct_observation_count == 2
    assert result.independent_root_count == 2
    assert result.sensor_types == (
        "BATHYMETRIC_LIDAR",
        "MULTIBEAM_ECHOSOUNDER",
    )


def test_pipeline_preserves_artifact_candidate_state() -> None:
    grid = obs(
        "grid",
        sensor=SensorType.DERIVED_BATHYMETRIC_GRID,
        stage=ProductStage.GRID,
        coverage=CoverageState.INTERPOLATED,
    )
    universe = validate_observation_universe((grid,))
    candidate = MarineFeatureCandidate(
        feature_id="tile-edge-001",
        morphology=GeomorphologyClass.LINEAR_FEATURE,
        observation_ids=("grid",),
        artifact_flags=("TILE_SEAM_COINCIDENCE", "SOURCE_BOUNDARY_COINCIDENCE"),
    )

    result = assess_marine_feature(candidate, universe)

    assert result.evidence_state is EvidenceState.ARTIFACT_CANDIDATE
    assert result.direct_observation_count == 0


def test_observation_universe_rejects_duplicate_stable_id() -> None:
    first = obs("same", root="a")
    second = obs("same", root="b")

    with pytest.raises(ValueError, match="duplicate marine observation_id"):
        validate_observation_universe((first, second))


def test_candidate_rejects_duplicate_observation_reference() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        MarineFeatureCandidate(
            feature_id="candidate",
            morphology=GeomorphologyClass.RIDGE,
            observation_ids=("a", "a"),
        )


def test_feature_assessment_rejects_missing_observation() -> None:
    candidate = MarineFeatureCandidate(
        feature_id="candidate",
        morphology=GeomorphologyClass.RIDGE,
        observation_ids=("missing",),
    )

    with pytest.raises(KeyError, match="unknown observation"):
        assess_marine_feature(candidate, {})


def test_temporal_comparison_requires_strict_time_order() -> None:
    earlier = obs("earlier", when=NOW)
    same_time = obs("same-time", when=NOW)

    with pytest.raises(ValueError, match="strictly newer"):
        compare_temporal_observations(earlier, same_time)


def test_temporal_comparison_propagates_uncertainty() -> None:
    earlier = obs("earlier", value=10.0, when=NOW)
    later = obs("later", value=10.5, when=NOW + timedelta(days=365))

    result = compare_temporal_observations(earlier, later)

    assert result.delta_b_minus_a_m == pytest.approx(0.5)
    assert result.combined_uncertainty_m == pytest.approx(2**0.5 * 0.25)
