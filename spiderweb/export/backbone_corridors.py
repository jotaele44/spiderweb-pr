from __future__ import annotations

import geopandas as gpd


HIGH_PRIORITY_THRESHOLD = 0.01


def classify_priority_corridors(linked_nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if linked_nodes.empty:
        return linked_nodes

    gdf = linked_nodes.copy()

    gdf["priority_class"] = "local"

    high_mask = (
        gdf["degree_centrality"].fillna(0)
        + gdf["betweenness_centrality"].fillna(0)
    ) >= HIGH_PRIORITY_THRESHOLD

    gdf.loc[high_mask, "priority_class"] = "backbone"

    return gdf
