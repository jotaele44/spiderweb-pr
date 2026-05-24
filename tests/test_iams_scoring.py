from spiderweb.scoring.convergence import score_convergence
from spiderweb.scoring.false_positive import apply_false_positive_controls


def test_score_convergence_adds_weights_and_class_bonus():
    signals = [
        {"signal_class": "Hydro", "weight": 20},
        {"signal_class": "WIDL", "weight": 30},
        {"signal_class": "Terrain", "weight": 15},
    ]
    assert score_convergence(10, signals) == 85


def test_score_convergence_caps_at_100():
    signals = [
        {"signal_class": "Hydro", "weight": 40},
        {"signal_class": "WIDL", "weight": 40},
        {"signal_class": "Terrain", "weight": 40},
        {"signal_class": "Utility", "weight": 40},
        {"signal_class": "Karst", "weight": 40},
    ]
    assert score_convergence(50, signals) == 100


def test_false_positive_controls_cap_single_vegetation_signal():
    score = apply_false_positive_controls(
        80,
        {
            "single_vegetation_signal_only": True,
            "hydro_or_utility_or_terrain_support": True,
        },
    )
    assert score == 45


def test_false_positive_controls_cap_no_support():
    score = apply_false_positive_controls(70, {})
    assert score == 50
