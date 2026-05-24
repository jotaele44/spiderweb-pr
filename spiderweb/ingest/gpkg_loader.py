from pathlib import Path

import geopandas as gpd
import fiona


class GPKGLoader:
    def __init__(self, gpkg_path: str):
        self.gpkg_path = Path(gpkg_path)

    def list_layers(self) -> list[str]:
        return fiona.listlayers(self.gpkg_path)

    def load_layer(self, layer_name: str) -> gpd.GeoDataFrame:
        return gpd.read_file(self.gpkg_path, layer=layer_name)
