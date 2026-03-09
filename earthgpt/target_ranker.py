"""
EarthGPT iOS — Target ranker.

Applies quality filters and produces the final ranked target list.
"""

from typing import List

from .ranking import rank_candidates


def filter_candidates(
    candidates: List[dict],
    min_score: float = 0.3,
    min_nodes: int = 1,
) -> List[dict]:
    """Filter candidates below quality thresholds."""
    return [
        c for c in candidates
        if float(c.get("max_score", 0.0)) >= min_score
        and int(c.get("node_count", 0)) >= min_nodes
    ]


def run_target_ranker(
    candidates: List[dict],
    min_score: float = 0.3,
    min_nodes: int = 1,
) -> List[dict]:
    """
    Filter, score, and rank corridor candidates.

    Returns sorted list of ranked target dicts.
    """
    filtered = filter_candidates(candidates, min_score=min_score, min_nodes=min_nodes)
    if not filtered:
        return []
    return rank_candidates(filtered)
