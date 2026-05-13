"""Tests for GeoCalibration modes and CoordResult."""

import pytest

from geo_calibration import CoordResult, GeoCalibration

PR_BOUNDS = {"north": 18.65, "south": 17.92, "east": -65.20, "west": -67.30}


def test_fixed_pr_bounds_mode_returns_coordresult():
    cal = GeoCalibration(mode="fixed_pr_bounds")
    result = cal.pixel_to_coord(512, 384, 1024, 768)
    assert isinstance(result, CoordResult)
    assert result.coordinate_method == "fixed_pr_bounds"
    assert result.coordinate_confidence == 0.65
    assert result.estimated_error_m == 1500.0


def test_fixed_pr_bounds_in_pr_bbox():
    cal = GeoCalibration(mode="fixed_pr_bounds")
    result = cal.pixel_to_coord(512, 384, 1024, 768)
    assert result.in_pr_bbox(), f"Result {result.lat},{result.lon} outside PR bbox"


def test_airport_anchor_mode_confidence():
    cal = GeoCalibration(mode="airport_anchor")
    result = cal.pixel_to_coord(512, 384, 1024, 768)
    assert result.coordinate_method == "airport_anchor"
    assert result.coordinate_confidence == 0.82
    assert result.estimated_error_m == 500.0


def test_manual_anchor_csv_requires_path():
    with pytest.raises(ValueError, match="requires anchors_csv"):
        GeoCalibration(mode="manual_anchor_csv")


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        GeoCalibration(mode="nonexistent_mode")


def test_coord_result_to_dict():
    r = CoordResult(lat=18.44, lon=-66.0, coordinate_method="fixed_pr_bounds",
                    coordinate_confidence=0.65, estimated_error_m=1500.0)
    d = r.to_dict()
    assert d["lat"] == 18.44
    assert d["coordinate_method"] == "fixed_pr_bounds"
    assert set(d.keys()) == {"lat", "lon", "coordinate_method",
                              "coordinate_confidence", "estimated_error_m"}


def test_generate_quality_report(tmp_path):
    cal = GeoCalibration(mode="fixed_pr_bounds")
    rows = [
        {"screenshot_id": f"SS_{i:03d}", "lat": 18.44, "lon": -66.0,
         "coordinate_method": "fixed_pr_bounds", "coordinate_confidence": 0.65,
         "estimated_error_m": 1500.0}
        for i in range(5)
    ]
    out = str(tmp_path / "quality_report.csv")
    count = cal.generate_quality_report(rows, out)
    assert count == 5
    import csv
    with open(out, newline="") as f:
        reader = csv.DictReader(f)
        report_rows = list(reader)
    assert len(report_rows) == 5
    assert "in_pr_bbox" in report_rows[0]


def test_zero_pixel_returns_sensible_result():
    cal = GeoCalibration(mode="fixed_pr_bounds")
    result = cal.pixel_to_coord(0, 0, 1024, 768)
    assert isinstance(result.lat, float)
    assert isinstance(result.lon, float)
