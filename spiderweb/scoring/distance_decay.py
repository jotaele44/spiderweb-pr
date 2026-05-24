def distance_decay_weight(base_weight: float, distance_m: float, max_distance_m: float = 500.0) -> float:
    """Linearly decay a signal weight by distance.

    Returns zero at or beyond max_distance_m. Distances below zero are treated as zero.
    """
    if max_distance_m <= 0:
        raise ValueError("max_distance_m must be positive")

    distance = max(0.0, float(distance_m))
    if distance >= max_distance_m:
        return 0.0

    factor = 1.0 - (distance / max_distance_m)
    return max(0.0, float(base_weight) * factor)
