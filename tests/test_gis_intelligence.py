"""Tests for GIS intelligence: haversine and corridor membership."""

import pytest

from gis_intelligence import (
    CorridorAnalyzer,
    PuertoRicoInfrastructure,
    haversine_nm,
)


def test_haversine_same_point():
    dist = haversine_nm(18.44, -66.0, 18.44, -66.0)
    assert dist == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # SJU → BQN: ~60 nm
    dist = haversine_nm(18.4373, -66.0018, 18.4948, -67.1294)
    assert 55 < dist < 70, f"Expected ~60 nm, got {dist:.1f}"


def test_infrastructure_loads():
    infra = PuertoRicoInfrastructure()
    assert infra is not None


def test_corridor_analyzer_find_corridors(populated_db):
    import sqlite3
    conn = sqlite3.connect(populated_db)
    conn.row_factory = sqlite3.Row
    track_pts = [dict(r) for r in conn.execute(
        "SELECT * FROM track_points WHERE flight_id = 'FLT_N5854Z_001'"
    )]
    conn.close()

    infra = PuertoRicoInfrastructure()
    analyzer = CorridorAnalyzer(infra)
    result = analyzer.find_corridors_for_flight(track_pts)
    assert isinstance(result, list)


def test_haversine_triangle_inequality():
    a = haversine_nm(18.0, -66.0, 18.5, -66.0)
    b = haversine_nm(18.5, -66.0, 18.5, -67.0)
    c = haversine_nm(18.0, -66.0, 18.5, -67.0)
    assert c <= a + b + 0.1  # triangle inequality with small tolerance


# ── Task 24: HeatmapGenerator.get_geojson() output structure ─────────────────

def test_heatmap_get_geojson_structure(populated_db):
    """HeatmapGenerator.get_geojson() must return valid GeoJSON (Task 24)."""
    import sqlite3, json
    from gis_intelligence import HeatmapGenerator
    conn = sqlite3.connect(populated_db)
    conn.row_factory = sqlite3.Row
    track_pts = [dict(r) for r in conn.execute("SELECT latitude, longitude FROM track_points")]
    conn.close()

    gen = HeatmapGenerator()
    for pt in track_pts:
        gen.add_point(pt.get("latitude", 18.4), pt.get("longitude", -66.0))

    geojson = gen.get_geojson()
    assert "type" in geojson, "GeoJSON must have 'type'"
    assert geojson["type"] in ("FeatureCollection", "Feature", "Point")


# ── Task 25: all PuertoRicoInfrastructure features have finite distance ───────

def test_all_infrastructure_features_distance_finite():
    """All PR infrastructure features must return finite float from distance_to_point (Task 25)."""
    import math
    infra = PuertoRicoInfrastructure()
    test_lat, test_lon = 18.4373, -66.0018  # SJU
    for fid, feature in infra.features.items():
        dist = feature.distance_to_point(test_lat, test_lon)
        assert isinstance(dist, float), f"{fid}: distance_to_point returned {type(dist)}"
        assert math.isfinite(dist), f"{fid}: distance_to_point returned non-finite {dist}"
        assert dist >= 0, f"{fid}: distance_to_point returned negative {dist}"
