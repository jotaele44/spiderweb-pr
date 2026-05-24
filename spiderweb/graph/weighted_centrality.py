from __future__ import annotations

import networkx as nx


class WeightedCentrality:
    @staticmethod
    def apply_edge_weights(graph: nx.Graph):
        for u, v, data in graph.edges(data=True):
            friction = float(data.get("terrain_friction", 1.0))
            distance_m = float(data.get("distance_m", 1.0))

            # Lower traversal weight for easier corridors.
            data["weight"] = max(0.0001, friction * distance_m)

    @staticmethod
    def compute_weighted_betweenness(graph: nx.Graph):
        return nx.betweenness_centrality(graph, weight="weight")

    @staticmethod
    def compute_weighted_degree(graph: nx.Graph):
        scores = {}
        for node in graph.nodes():
            total = 0.0
            for _, _, data in graph.edges(node, data=True):
                total += 1.0 / max(data.get("weight", 1.0), 0.0001)
            scores[node] = total
        return scores
