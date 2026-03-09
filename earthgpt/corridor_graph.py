"""
EarthGPT iOS — Corridor graph construction.

Clusters nearby, aligned anomaly nodes and seams into corridor candidates.
"""

import math
from typing import List, Tuple


def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate Euclidean distance in degrees."""
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)


def _centroid(nodes: List[dict]) -> Tuple[float, float]:
    lats = [n.get("lat", 0.0) for n in nodes]
    lons = [n.get("lon", 0.0) for n in nodes]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def build_corridor_candidates(
    nodes: List[dict],
    seams: List[dict],
    max_gap_deg: float = 0.01,
    min_tiles: int = 2,
) -> List[dict]:
    """
    Cluster anomaly nodes by proximity into corridor candidates.

    Each candidate contains a list of node_ids and aggregate metrics.
    """
    if not nodes:
        return []

    # Simple greedy spatial clustering
    assigned = [False] * len(nodes)
    clusters: List[dict] = []

    for i in range(len(nodes)):
        if assigned[i]:
            continue
        cluster_nodes = [nodes[i]]
        assigned[i] = True

        for j in range(i + 1, len(nodes)):
            if assigned[j]:
                continue
            dist = _distance(
                nodes[i].get("lat", 0.0),
                nodes[i].get("lon", 0.0),
                nodes[j].get("lat", 0.0),
                nodes[j].get("lon", 0.0),
            )
            if dist <= max_gap_deg:
                cluster_nodes.append(nodes[j])
                assigned[j] = True

        if len(cluster_nodes) < min_tiles:
            continue

        scores = [float(n.get("score", 0.0)) for n in cluster_nodes]
        risks = [float(n.get("risk_final_v2_0_100", 0.0)) for n in cluster_nodes]
        lat_c, lon_c = _centroid(cluster_nodes)

        clusters.append(
            {
                "corridor_id": f"corridor_{len(clusters)}",
                "node_count": len(cluster_nodes),
                "node_ids": [n.get("node_id", "") for n in cluster_nodes],
                "centroid_lat": round(lat_c, 6),
                "centroid_lon": round(lon_c, 6),
                "mean_score": round(sum(scores) / len(scores), 4),
                "max_score": round(max(scores), 4),
                "mean_risk": round(sum(risks) / len(risks), 2),
                "max_risk": round(max(risks), 2),
            }
        )

    return clusters
