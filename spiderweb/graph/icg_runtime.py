from __future__ import annotations

import geopandas as gpd

from spiderweb.graph.icg_builder import ICGBuilder
from spiderweb.graph.spatial_linking import SpatialLinker
from spiderweb.ingest.widl_extractor import (
    extract_icg_edges,
    extract_widl_nodes,
)


PROJECTED_CRS = "EPSG:3857"


def build_real_icg(gpkg_path: str):
    nodes = extract_widl_nodes(gpkg_path)
    edges = extract_icg_edges(gpkg_path)

    if nodes.empty or edges.empty:
        return {
            "nodes": nodes,
            "edges": edges,
            "graph": ICGBuilder(),
            "linked_nodes": nodes,
            "degree": {},
            "betweenness": {},
        }

    nodes_projected = nodes.to_crs(PROJECTED_CRS)
    edges_projected = edges.to_crs(PROJECTED_CRS)

    linker = SpatialLinker(snap_distance_m=150.0)
    linked_nodes = linker.snap_nodes_to_edges(nodes_projected, edges_projected)

    builder = ICGBuilder()

    for _, node in linked_nodes.iterrows():
        builder.add_node(
            node["node_id"],
            node_type=node["node_type"],
            source_layer=node["source_layer"],
        )

    for _, edge in edges.iterrows():
        edge_id = edge["edge_id"]
        builder.add_node(edge_id, edge_type=edge["edge_type"])

    for _, node in linked_nodes.iterrows():
        edge_idx = node.get("index_right")
        if edge_idx is None:
            continue

        edge_id = edges.iloc[int(edge_idx)]["edge_id"]
        builder.add_edge(
            node["node_id"],
            edge_id,
            distance_m=float(node["distance_m"]),
        )

    degree = builder.compute_degree_centrality()
    betweenness = builder.compute_betweenness_centrality()

    linked_nodes = linked_nodes.copy()
    linked_nodes["degree_centrality"] = linked_nodes["node_id"].map(degree)
    linked_nodes["betweenness_centrality"] = linked_nodes["node_id"].map(
        betweenness
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "graph": builder,
        "linked_nodes": linked_nodes,
        "degree": degree,
        "betweenness": betweenness,
    }
