"""Tests for earthgpt.metrics and earthgpt.features_lite."""

import pytest


def test_compute_node_metrics_empty_zooms():
    from earthgpt.metrics import compute_node_metrics
    result = compute_node_metrics({})
    assert isinstance(result, dict)
    assert "score" in result
    assert "decision" in result
    assert "risk_final_v2_0_100" in result
    assert "status" in result
    assert result["status"] != "ok"  # no zooms → fallback/no_zooms


def test_compute_node_metrics_none_images():
    from earthgpt.metrics import compute_node_metrics
    result = compute_node_metrics({15: None, 16: None})
    assert isinstance(result, dict)
    assert "score" in result
    assert result["score"] >= 0.0


def test_compute_single_metrics_none():
    from earthgpt.metrics import compute_single_metrics
    result = compute_single_metrics(None)
    assert isinstance(result, dict)
    assert result["status"] == "no_image"
    assert "score" in result


def test_extract_features_none():
    from earthgpt.features_lite import extract_features
    feats = extract_features(None)
    assert isinstance(feats, dict)
    assert "risk_final_v2_0_100" in feats
    assert feats["risk_final_v2_0_100"] >= 0.0


def test_risk_score_range():
    from earthgpt.features_lite import compute_risk_score
    score = compute_risk_score(3.0, 0.05, 0.02, 0.8)
    assert 0.0 <= score <= 100.0


def test_metrics_with_real_image():
    """Test metrics with a synthetic PIL image if libraries available."""
    try:
        import numpy as np
        from PIL import Image
        from earthgpt.metrics import compute_single_metrics

        arr = (np.random.rand(256, 256, 3) * 255).astype("uint8")
        img = Image.fromarray(arr)
        result = compute_single_metrics(img, zoom=15)
        assert result["status"] == "ok"
        assert 0.0 <= result["score"] <= 1.0
        assert 0.0 <= result["risk_final_v2_0_100"] <= 100.0
    except ImportError:
        pytest.skip("numpy or Pillow not available")
