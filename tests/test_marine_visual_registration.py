from __future__ import annotations

import pytest

from pipeline.marine_reference_run import GeometryRole
from pipeline.marine_visual_registration import (
    RegistrationControlPoint,
    RegistrationPolicy,
    fit_affine_registration,
    registered_visualization_aoi,
)


def _point(label: str, x: float, y: float, lon: float, lat: float):
    return RegistrationControlPoint(
        label=label,
        pixel_x=x,
        pixel_y=y,
        lon=lon,
        lat=lat,
        source_uri=f"https://example.test/{label}",
        source_sha256="a" * 64,
    )


def test_perfect_affine_registration_certifies_under_explicit_policy() -> None:
    points = [
        _point("nw", 0, 0, -66.2, 18.05),
        _point("ne", 1000, 0, -65.8, 18.05),
        _point("sw", 0, 1100, -66.2, 17.5),
        _point("se", 1000, 1100, -65.8, 17.5),
    ]
    policy = RegistrationPolicy(
        min_control_points=4,
        max_rmse_m=1.0,
        max_point_error_m=2.0,
    )
    result = fit_affine_registration(points, policy)
    assert result.certified is True
    assert result.matrix_rank == 3
    assert result.control_point_count == 4
    assert result.rmse_m < 1e-5
    assert len(result.registration_id) == 64

    lon, lat = result.pixel_to_lonlat(500, 550)
    assert lon == pytest.approx(-66.0)
    assert lat == pytest.approx(17.775)


def test_noisy_registration_fails_closed_when_policy_is_exceeded() -> None:
    points = [
        _point("a", 0, 0, -66.2, 18.05),
        _point("b", 1000, 0, -65.8, 18.05),
        _point("c", 0, 1000, -66.2, 17.55),
        _point("d", 1000, 1000, -65.79, 17.55),
    ]
    policy = RegistrationPolicy(
        min_control_points=4,
        max_rmse_m=100.0,
        max_point_error_m=200.0,
    )
    result = fit_affine_registration(points, policy)
    assert result.certified is False
    assert result.max_error_m > 200.0


def test_degenerate_control_points_are_rejected() -> None:
    points = [
        _point("a", 0, 0, -66.2, 18.05),
        _point("b", 100, 100, -66.1, 18.0),
        _point("c", 200, 200, -66.0, 17.95),
    ]
    policy = RegistrationPolicy(
        min_control_points=3,
        max_rmse_m=100.0,
        max_point_error_m=200.0,
    )
    with pytest.raises(ValueError, match="degenerate"):
        fit_affine_registration(points, policy)


def test_registered_aoi_certification_tracks_registration_result() -> None:
    points = [
        _point("nw", 0, 0, -66.2, 18.05),
        _point("ne", 1000, 0, -65.8, 18.05),
        _point("sw", 0, 1100, -66.2, 17.5),
        _point("se", 1000, 1100, -65.8, 17.5),
    ]
    policy = RegistrationPolicy(
        min_control_points=4,
        max_rmse_m=1.0,
        max_point_error_m=2.0,
    )
    registration = fit_affine_registration(points, policy)
    aoi = registered_visualization_aoi(
        registration,
        image_width_px=1001,
        image_height_px=1101,
        aoi_id="screenshot_registered_v0_1",
    )
    assert aoi.role is GeometryRole.REGISTERED_VISUALIZATION
    assert aoi.certified is True
    aoi.require_visualization_certification()
    assert aoi.bbox.min_lon == pytest.approx(-66.2)
    assert aoi.bbox.max_lon == pytest.approx(-65.8)
    assert aoi.bbox.min_lat == pytest.approx(17.5)
    assert aoi.bbox.max_lat == pytest.approx(18.05)


def test_registration_policy_has_no_silent_zero_or_negative_threshold() -> None:
    with pytest.raises(ValueError, match="positive"):
        RegistrationPolicy(min_control_points=4, max_rmse_m=0.0, max_point_error_m=1.0)


def test_duplicate_labels_are_rejected() -> None:
    points = [
        _point("same", 0, 0, -66.2, 18.05),
        _point("same", 1000, 0, -65.8, 18.05),
        _point("c", 0, 1000, -66.2, 17.55),
    ]
    policy = RegistrationPolicy(
        min_control_points=3,
        max_rmse_m=100.0,
        max_point_error_m=200.0,
    )
    with pytest.raises(ValueError, match="labels must be unique"):
        fit_affine_registration(points, policy)
