from __future__ import annotations

import geopandas as gpd


DEVIATION_THRESHOLDS = {
    "low": 1.0,
    "moderate": 1.5,
    "high": 2.0,
}


def classify_corridor_deviation(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf

    out = gdf.copy()

    out["deviation_ratio"] = (
        out["real_cost"].fillna(1.0)
        / out["optimal_cost"].replace(0, 1.0).fillna(1.0)
    )

    out["deviation_class"] = "low"
    out.loc[
        out["deviation_ratio"] >= DEVIATION_THRESHOLDS["moderate"],
        "deviation_class",
    ] = "moderate"
    out.loc[
        out["deviation_ratio"] >= DEVIATION_THRESHOLDS["high"],
        "deviation_class",
    ] = "high"

    return out
