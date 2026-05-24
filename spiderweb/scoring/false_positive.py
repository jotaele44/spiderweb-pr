def apply_false_positive_controls(score: float, context: dict) -> float:
    if context.get("dense_residential"):
        score -= 20

    if context.get("golf_or_resort") and not context.get("utility_link"):
        score -= 20

    if context.get("single_vegetation_signal_only"):
        score = min(score, 45)

    if not context.get("hydro_or_utility_or_terrain_support"):
        score = min(score, 50)

    return max(0, min(100, score))
