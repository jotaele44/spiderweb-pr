def score_convergence(base_confidence: float, signals: list[dict]) -> float:
    total = base_confidence
    classes = set()

    for signal in signals:
        total += signal.get("weight", 0)
        classes.add(signal.get("signal_class"))

    if len(classes) >= 3:
        total += 10

    if len(classes) >= 5:
        total += 15

    return max(0, min(100, total))
