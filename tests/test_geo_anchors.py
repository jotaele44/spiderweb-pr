from pipeline.geo_anchors import GeoAnchor, fit_homography
from pipeline.flight_analyzer import CoordinateMapper


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
    assert (lon, lat) == (-65.5, 18.5)


def test_coordinate_mapper_uses_derived_fit_only_when_evidence_is_sufficient():
    mapper = CoordinateMapper(100, 100)
    assert mapper.fit_derived_anchors([GeoAnchor(0, 0, -66, 18)] * 3) is None
    anchors = [
        GeoAnchor(0, 0, -66, 18), GeoAnchor(100, 0, -65, 18),
        GeoAnchor(0, 100, -66, 19), GeoAnchor(100, 100, -65, 19),
    ]
    assert mapper.fit_derived_anchors(anchors) is not None
    assert mapper.pixel_to_latlon(50, 50) == (18.5, -65.5)
