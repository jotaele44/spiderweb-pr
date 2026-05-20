"""Tests for EarthGPT iOS pipeline additions: dry_run, from_flight_event, validate, ios_profile."""

import pytest


# ── dry_run ───────────────────────────────────────────────────────────────────

def test_dry_run_valid_nodes():
    from earthgpt.pipeline import dry_run
    nodes = [{"x": 100, "y": 200, "zoom": 15}, {"x": 101, "y": 200, "zoom": 15}]
    result = dry_run(nodes)
    assert result["ready"] is True
    assert result["valid_count"] == 2
    assert result["invalid"] == []


def test_dry_run_missing_key():
    from earthgpt.pipeline import dry_run
    nodes = [{"x": 100, "y": 200}]  # missing zoom
    result = dry_run(nodes)
    assert result["ready"] is False
    assert len(result["invalid"]) == 1
    assert "zoom" in result["invalid"][0][1]


def test_dry_run_wrong_type():
    from earthgpt.pipeline import dry_run
    nodes = [{"x": "bad", "y": 200, "zoom": 15}]
    result = dry_run(nodes)
    assert result["ready"] is False


def test_dry_run_empty_list():
    from earthgpt.pipeline import dry_run
    result = dry_run([])
    assert result["ready"] is True
    assert result["valid_count"] == 0


def test_dry_run_not_a_dict():
    from earthgpt.pipeline import dry_run
    result = dry_run(["not a dict"])
    assert result["ready"] is False


# ── TileContext.from_flight_event / to_schema_dict ────────────────────────────

def test_from_flight_event_returns_tile_context():
    from earthgpt.context import TileContext
    fe = {"flight_id": "FLT_001", "callsign": "N5854Z",
          "origin_lat": 18.44, "origin_lon": -66.0}
    ctx = TileContext.from_flight_event(fe)
    assert isinstance(ctx, TileContext)


def test_from_flight_event_to_schema_dict_has_required_keys():
    from earthgpt.context import TileContext
    ctx = TileContext.from_flight_event({"flight_id": "x", "callsign": "y"})
    d = ctx.to_schema_dict()
    for key in ("tile_x", "tile_y", "zoom", "tile_type"):
        assert key in d, f"Missing key: {key}"


# ── ContextNormalizer.validate ────────────────────────────────────────────────

def test_context_normalizer_validate_valid():
    from earthgpt.context_normalizer import validate
    validate({"x": 0, "y": 0, "zoom": 15, "tile_type": "land"})  # no raise


def test_context_normalizer_validate_missing_field():
    from earthgpt.context_normalizer import validate
    with pytest.raises(ValueError, match="missing required fields"):
        validate({"x": 0, "y": 0, "zoom": 15})  # missing tile_type


def test_context_normalizer_validate_invalid_tile_type():
    from earthgpt.context_normalizer import validate
    with pytest.raises(ValueError, match="tile_type must be one of"):
        validate({"x": 0, "y": 0, "zoom": 15, "tile_type": "forest"})


# ── ios_profile.memory_budget_mb / for_device ────────────────────────────────

def test_memory_budget_mb_known_device():
    from earthgpt.ios_profile import memory_budget_mb
    budget = memory_budget_mb("iphone_14")
    assert budget > 0
    assert budget <= 6144 // 2 + 1


def test_memory_budget_mb_default_device():
    from earthgpt.ios_profile import memory_budget_mb
    budget = memory_budget_mb("unknown_device_xyz")
    assert budget == 2048 // 2


def test_for_device_returns_dict():
    from earthgpt.ios_profile import for_device
    profile = for_device("iphone_12")
    assert isinstance(profile, dict)


def test_for_device_has_memory_budget():
    from earthgpt.ios_profile import for_device
    profile = for_device("ipad_pro")
    assert "memory_budget_mb" in profile
    assert profile["memory_budget_mb"] > 0


def test_for_device_tile_cache_limit_positive():
    from earthgpt.ios_profile import for_device
    profile = for_device("iphone_15")
    assert profile["tile_cache_limit"] >= 1
