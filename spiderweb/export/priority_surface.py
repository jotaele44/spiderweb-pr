from __future__ import annotations

import geopandas as gpd


PRIORITY_FIELDS = [
    "degree_centrality",
    "betweenness_centrality",
    "weighted_degree",
    "weighted_betweenness",
]


def prepare_priority_surface(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf

    out = gdf.copy()

    for field in PRIORITY_FIELDS:
        if field not in out.columns:
            out[field] = 0.0

    out["priority_score"] = (
        out["degree_centrality"].fillna(0)
        + out["betweenness_centrality"].fillna(0)
        + out["weighted_degree"].fillna(0)
        + out["weighted_betweenness"].fillna(0)
    )

    return out
