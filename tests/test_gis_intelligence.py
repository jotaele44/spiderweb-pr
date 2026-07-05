"""Tests for GIS intelligence: haversine and corridor membership."""

import pytest

from pipeline.gis_intelligence import (
    AnomalyDetector,
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


def test_detect_unusual_patterns_flags_off_hours():
    detector = AnomalyDetector(PuertoRicoInfrastructure())
    anomalies = detector.detect_unusual_patterns(
        {"operator": "PREPA", "takeoff_time": "2024-03-15T03:00:00"}
    )
    assert any(a["type"] == "unusual_time" for a in anomalies)


def test_detect_unusual_patterns_normal_hours_no_time_anomaly():
    detector = AnomalyDetector(PuertoRicoInfrastructure())
    anomalies = detector.detect_unusual_patterns(
        {"operator": "PREPA", "takeoff_time": "2024-03-15T10:00:00"}
    )
    assert not any(a["type"] in ("unusual_time", "unparseable_takeoff_time") for a in anomalies)


def test_detect_unusual_patterns_malformed_time_is_not_swallowed():
    """A malformed takeoff_time must surface an anomaly, not be silently dropped."""
    detector = AnomalyDetector(PuertoRicoInfrastructure())
    anomalies = detector.detect_unusual_patterns(
        {"operator": "PREPA", "takeoff_time": "not-a-timestamp"}
    )
    assert any(a["type"] == "unparseable_takeoff_time" for a in anomalies)
