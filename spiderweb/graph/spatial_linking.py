import geopandas as gpd


class SpatialLinker:
    def __init__(self, snap_distance_m: float = 150.0):
        self.snap_distance_m = snap_distance_m

    def snap_nodes_to_edges(
        self,
        nodes_gdf: gpd.GeoDataFrame,
        edges_gdf: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        """Attach nearest edge index and distance to each node.

        Assumes projected CRS in meters.
        """
        if nodes_gdf.empty or edges_gdf.empty:
            return nodes_gdf.copy()

        joined = gpd.sjoin_nearest(
            nodes_gdf,
            edges_gdf,
            how="left",
            distance_col="distance_m",
        )

        return joined[joined["distance_m"] <= self.snap_distance_m].copy()
