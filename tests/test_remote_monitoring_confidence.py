"""Confidence scoring and band-classification tests."""

from spiderweb.remote_monitoring import assess, classify, schemas, score_confidence


def test_component_weights_sum_to_100():
    assert sum(schemas.CONFIDENCE_COMPONENTS.values()) == 100


def test_all_components_max_scores_100():
    full = {k: 1.0 for k in schemas.CONFIDENCE_COMPONENTS}
    assert score_confidence(full) == 100.0
    assert classify(100.0) == "high_confidence_change"


def test_empty_components_score_zero_weak_signal():
    assert score_confidence({}) == 0.0
    assert classify(0.0) == "weak_signal"


def test_inputs_are_clamped():
    # A mis-scaled >1 input cannot push the total past its component weight.
    over = {k: 5.0 for k in schemas.CONFIDENCE_COMPONENTS}
    assert score_confidence(over) == 100.0
    neg = {"sensor_quality": -3.0}
    assert score_confidence(neg) == 0.0


def test_band_boundaries():
    assert classify(84.99) == "corroborated_change"
    assert classify(85) == "high_confidence_change"
    assert classify(70) == "corroborated_change"
    assert classify(69.99) == "supported_candidate"
    assert classify(50) == "supported_candidate"
    assert classify(30) == "candidate"
    assert classify(29.99) == "weak_signal"


def test_unknown_components_ignored():
    score = score_confidence({"not_a_component": 1.0, "sensor_quality": 1.0})
    assert score == 15.0  # only sensor_quality (max 15) counts


def test_assess_returns_score_band_and_components():
    result = assess({"independent_corroboration": 1.0, "sensor_quality": 1.0})
    assert result["score"] == 35.0
    assert result["band"] == "candidate"
    assert set(result["components"]) == set(schemas.CONFIDENCE_COMPONENTS)
