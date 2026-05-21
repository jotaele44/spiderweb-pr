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


# ── Stage 1 hardening tests ───────────────────────────────────────────────────

def test_manual_anchor_csv_interpolates_from_csv(tmp_path):
    anchor_csv = tmp_path / "anchors.csv"
    anchor_csv.write_text(
        "anchor_id,name,pixel_x_fraction,pixel_y_fraction,lat,lon\n"
        "SJU,San Juan Airport,0.70,0.30,18.4373,-66.0018\n"
        "BQN,Rafael Hernandez Airport,0.15,0.28,18.4948,-67.1294\n"
    )
    cal = GeoCalibration(mode="manual_anchor_csv", anchors_csv=str(anchor_csv))
    result = cal.pixel_to_coord(512, 300, 1024, 768)
    assert isinstance(result, CoordResult)
    assert result.coordinate_method == "manual_anchor_csv"
    assert result.coordinate_confidence == 0.90
    assert result.in_pr_bbox(), (
        f"Interpolated coord {result.lat},{result.lon} should be within PR bbox"
    )


# ── Tasks 22-23: multi_anchor_weighted mode + GeoCalibrationConfig round-trip ─

import pytest

@pytest.mark.parametrize("mode", ["fixed_pr_bounds", "airport_anchor", "manual_anchor_csv"])
def test_all_calibration_modes_return_coord_result(tmp_path, mode):
    """All three modes must return a CoordResult within PR bounds (Task 22)."""
    anchor_csv = tmp_path / "anchors.csv"
    anchor_csv.write_text(
        "anchor_id,name,pixel_x_fraction,pixel_y_fraction,lat,lon\n"
        "SJU,San Juan Airport,0.70,0.30,18.4373,-66.0018\n"
    )
    kwargs = {}
    if mode in ("airport_anchor", "manual_anchor_csv"):
        kwargs["anchors_csv"] = str(anchor_csv)
    cal = GeoCalibration(mode=mode, **kwargs)
    result = cal.pixel_to_coord(512, 300, 1024, 768)
    assert isinstance(result, CoordResult)
    assert result.coordinate_method == mode


def test_multi_anchor_weighted_mode(tmp_path):
    """multi_anchor_weighted IDW mode returns a valid CoordResult (Task 22)."""
    anchor_csv = tmp_path / "anchors.csv"
    anchor_csv.write_text(
        "anchor_id,name,pixel_x_fraction,pixel_y_fraction,lat,lon\n"
        "SJU,San Juan Airport,0.70,0.30,18.4373,-66.0018\n"
        "BQN,Rafael Hernandez Airport,0.15,0.28,18.4948,-67.1294\n"
    )
    cal = GeoCalibration(mode="multi_anchor_weighted", anchors_csv=str(anchor_csv))
    result = cal.pixel_to_coord(512, 300, 1024, 768)
    assert isinstance(result, CoordResult)
    assert result.coordinate_method == "multi_anchor_weighted"
    assert 17.5 <= result.lat <= 19.5
    assert -68.0 <= result.lon <= -64.5


def test_geo_calibration_config_round_trip():
    """GeoCalibrationConfig serialises and deserialises correctly (Task 23)."""
    import json
    from geo_calibration import GeoCalibrationConfig
    cfg = GeoCalibrationConfig(map_top_fraction=0.12, map_bottom_fraction=0.80)
    as_dict = {"map_top_fraction": cfg.map_top_fraction, "map_bottom_fraction": cfg.map_bottom_fraction}
    json_str = json.dumps(as_dict)
    restored = GeoCalibrationConfig(**json.loads(json_str))
    assert restored.map_top_fraction == 0.12
    assert restored.map_bottom_fraction == 0.80


def test_benchmark_all_modes(tmp_path):
    """benchmark() returns an entry for every mode (Task 50)."""
    anchor_csv = tmp_path / "anchors.csv"
    anchor_csv.write_text(
        "anchor_id,name,pixel_x_fraction,pixel_y_fraction,lat,lon\n"
        "SJU,San Juan Airport,0.70,0.30,18.4373,-66.0018\n"
    )
    cal = GeoCalibration(mode="fixed_pr_bounds")
    results = cal.benchmark(px=512, py=300, img_w=1024, img_h=768, anchors_csv=str(anchor_csv))
    for mode in ("fixed_pr_bounds", "airport_anchor", "multi_anchor_weighted"):
        assert mode in results, f"Mode {mode!r} missing from benchmark results"
        assert "lat" in results[mode]
        assert "confidence" in results[mode]
