"""
EarthGPT iOS — Candidate ranking helpers.

Scores and sorts corridor candidates for target ranking.
"""

from typing import List


def score_candidate(candidate: dict) -> float:
    """
    Compute a composite ranking score for a corridor candidate.

    Combines max_score, mean_risk, and node_count for a holistic rank.
    """
    max_score = float(candidate.get("max_score", 0.0))
    mean_risk = float(candidate.get("mean_risk", 0.0)) / 100.0
    node_count_bonus = min(float(candidate.get("node_count", 1)) / 20.0, 1.0)

    return 0.5 * max_score + 0.3 * mean_risk + 0.2 * node_count_bonus


def rank_candidates(candidates: List[dict]) -> List[dict]:
    """
    Add a ``rank_score`` and ``rank`` field to each candidate,
    sorted by rank_score descending.
    """
    for c in candidates:
        c["rank_score"] = round(score_candidate(c), 4)

    sorted_candidates = sorted(candidates, key=lambda c: c["rank_score"], reverse=True)
    for i, c in enumerate(sorted_candidates, 1):
        c["rank"] = i

    return sorted_candidates
