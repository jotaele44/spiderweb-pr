"""Tests for TemporalValidator physics violation detection."""

import pytest


def test_temporal_validator_import():
    from pipeline.hardening_layer import TemporalValidator
    tv = TemporalValidator()
    assert tv is not None


def test_validate_clean_track():
    from pipeline.hardening_layer import TemporalValidator
    tv = TemporalValidator()

    # Well-behaved track: sequential timestamps, moderate speeds
    points = [
        {"timestamp": f"2024-03-15T08:{i:02d}:00", "latitude": 18.44 + i * 0.01,
         "longitude": -66.00 + i * 0.01, "ground_speed_mph": 100, "altitude_ft": 3000}
        for i in range(5)
    ]
    results = tv.validate_track(points)
    violations = tv.count_violations(results)
    assert violations == 0


def test_validate_track_with_teleport():
    from pipeline.hardening_layer import TemporalValidator
    tv = TemporalValidator()

    # Two points 1 second apart but 500 km away — impossible speed
    points = [
        {"timestamp": "2024-03-15T08:00:00", "latitude": 18.44, "longitude": -66.00,
         "ground_speed_mph": 100, "altitude_ft": 3000},
        {"timestamp": "2024-03-15T08:00:01", "latitude": 23.00, "longitude": -70.00,
         "ground_speed_mph": 100, "altitude_ft": 3000},
    ]
    results = tv.validate_track(points)
    violations = tv.count_violations(results)
    assert violations >= 1


def test_count_violations_empty_track():
    from pipeline.hardening_layer import TemporalValidator
    tv = TemporalValidator()
    results = tv.validate_track([])
    assert tv.count_violations(results) == 0
