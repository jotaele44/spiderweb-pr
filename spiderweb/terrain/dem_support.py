from __future__ import annotations

import rasterio
from rasterio.sample import sample_gen


class DEMSampler:
    def __init__(self, dem_path: str):
        self.dem_path = dem_path

    def sample_elevation(self, coordinates: list[tuple[float, float]]):
        with rasterio.open(self.dem_path) as src:
            values = list(sample_gen(src, coordinates))
        return [float(v[0]) for v in values]
