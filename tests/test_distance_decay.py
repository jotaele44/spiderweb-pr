from spiderweb.scoring.distance_decay import distance_decay_weight


def test_distance_decay_full_weight_at_zero_distance():
    assert distance_decay_weight(20, 0) == 20


def test_distance_decay_half_weight_midway():
    assert distance_decay_weight(20, 250, 500) == 10


def test_distance_decay_zero_beyond_threshold():
    assert distance_decay_weight(20, 600, 500) == 0
