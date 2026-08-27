import pytest

from pipeline.geo_anchors import GeoAnchor, fit_homography


def test_homography_requires_four_anchor_matches():
    assert fit_homography([GeoAnchor(0, 0, -66, 18)] * 3) is None


def test_homography_projects_known_anchor_geometry():
    anchors = [
        GeoAnchor(0, 0, -66, 18),
        GeoAnchor(100, 0, -65, 18),
        GeoAnchor(0, 100, -66, 19),
        GeoAnchor(100, 100, -65, 19),
    ]
    fit = fit_homography(anchors)
    assert fit is not None
    lon, lat = fit.project(50, 50)
    assert (lon, lat) == pytest.approx((-65.5, 18.5))
    assert fit.rms_error_px == pytest.approx(0, abs=1e-9)


def test_homography_rejects_degenerate_anchor_geometry():
    assert fit_homography([GeoAnchor(0, 0, -66, 18)] * 4) is None


@pytest.mark.parametrize(
    "bad_anchor",
    (
        GeoAnchor(float("nan"), 100, -65, 19),
        GeoAnchor(100, 100, 181, 19),
        GeoAnchor(100, 100, -65, 91),
    ),
)
def test_homography_rejects_nonfinite_or_out_of_range_anchors(bad_anchor):
    anchors = [
        GeoAnchor(0, 0, -66, 18),
        GeoAnchor(100, 0, -65, 18),
        GeoAnchor(0, 100, -66, 19),
        bad_anchor,
    ]
    assert fit_homography(anchors) is None


def test_homography_rejects_nonpositive_error_bounds():
    anchors = [
        GeoAnchor(0, 0, -66, 18),
        GeoAnchor(100, 0, -65, 18),
        GeoAnchor(0, 100, -66, 19),
        GeoAnchor(100, 100, -65, 19),
    ]
    assert fit_homography(anchors, max_rms_error_px=0) is None
    assert fit_homography(anchors, ransac_threshold_px=0) is None


def test_homography_ransac_and_rms_gates_use_pixel_units():
    anchors = [
        GeoAnchor(0, 0, -66, 18),
        GeoAnchor(100, 0, -65, 18),
        GeoAnchor(0, 100, -66, 19),
        GeoAnchor(100, 100, -65, 19),
        GeoAnchor(80, 80, -65.5, 18.5),
    ]

    robust_fit = fit_homography(anchors, max_rms_error_px=1, ransac_threshold_px=3)
    assert robust_fit is not None
    assert robust_fit.anchor_count == 4
    assert robust_fit.rms_error_px < 1e-6
    assert fit_homography(anchors, max_rms_error_px=1, ransac_threshold_px=100) is None
