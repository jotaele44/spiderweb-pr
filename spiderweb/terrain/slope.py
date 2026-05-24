from __future__ import annotations

import numpy as np
import rasterio


def derive_slope_degrees(dem_array, x_resolution: float, y_resolution: float):
    """Derive slope in degrees from a DEM array.

    The calculation uses numpy gradient and expects horizontal units to match
    the DEM elevation units.
    """
    dz_dy, dz_dx = np.gradient(dem_array, y_resolution, x_resolution)
    slope_radians = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    return np.degrees(slope_radians)


def derive_slope_raster(dem_path: str, output_path: str):
    with rasterio.open(dem_path) as src:
        dem = src.read(1, masked=True).filled(np.nan)
        transform = src.transform
        slope = derive_slope_degrees(
            dem,
            abs(transform.a),
            abs(transform.e),
        ).astype("float32")

        profile = src.profile.copy()
        profile.update(dtype="float32", count=1, nodata=np.nan)

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(slope, 1)

    return output_path
