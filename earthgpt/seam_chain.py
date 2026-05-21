"""
EarthGPT iOS — Seam chain builder.

Chains individual seam pairs into longer contiguous structures.
"""

from typing import Dict, List, Tuple


def _endpoints(seam: dict) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    return (int(seam["x1"]), int(seam["y1"])), (int(seam["x2"]), int(seam["y2"]))


def build_seam_chains(seams: List[dict]) -> List[dict]:
    """
    Chain seams into linear / near-linear structures using union-find.

    Returns a list of chain dicts with seam_ids and aggregate score.
    """
    if not seams:
        return []

    # Build adjacency list on endpoints
    adj: Dict[Tuple[int, int], List[int]] = {}
    for idx, s in enumerate(seams):
        a, b = _endpoints(s)
        adj.setdefault(a, []).append(idx)
        adj.setdefault(b, []).append(idx)

    visited_seams = set()
    chains = []
    chain_id = 0

    for start_idx in range(len(seams)):
        if start_idx in visited_seams:
            continue

        # BFS from this seam
        queue = [start_idx]
        chain_seam_ids = []
        chain_scores = []
        while queue:
            idx = queue.pop(0)
            if idx in visited_seams:
                continue
            visited_seams.add(idx)
            s = seams[idx]
            chain_seam_ids.append(s["seam_id"])
            chain_scores.append(s["seam_score"])
            a, b = _endpoints(s)
            for nb_idx in adj.get(a, []) + adj.get(b, []):
                if nb_idx not in visited_seams:
                    queue.append(nb_idx)

        avg_score = sum(chain_scores) / len(chain_scores) if chain_scores else 0.0
        chains.append(
            {
                "chain_id": f"chain_{chain_id}",
                "seam_count": len(chain_seam_ids),
                "seam_ids": chain_seam_ids,
                "mean_seam_score": round(avg_score, 4),
                "max_seam_score": round(max(chain_scores), 4) if chain_scores else 0.0,
            }
        )
        chain_id += 1

    return chains


def confidence_weighted_path(chains: List[dict]) -> List[dict]:
    """Return path prioritizing high-confidence links."""
    if not chains:
        return []
    return sorted(chains, key=lambda c: c.get("mean_seam_score", 0), reverse=True)
