import geopandas as gpd


def export_geojson(gdf: gpd.GeoDataFrame, output_path: str):
    gdf.to_file(output_path, driver="GeoJSON")
