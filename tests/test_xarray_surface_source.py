import numpy as np
import pytest

xr = pytest.importorskip("xarray")

from federation.surface_analysis import MeasurementClass, SpatialState
from federation.surface_engine import SurfaceManifestation
from federation.xarray_surface_source import XarraySurfaceSource


def _manifestation():
    return SurfaceManifestation(
        "fixture", "fixture-source", "TEST", "EPSG:4326", "PRVD02",
        "positive_up", 3.43, MeasurementClass.MODELED, "0" * 64, "test",
    )


def test_source_native_sampling_preserves_ocean_and_nodata(tmp_path):
    path = tmp_path / "surface.nc"
    xr.Dataset(
        {"Band1": (("lat", "lon"), np.array([[-10.0, np.nan], [4.0, 8.0]]))},
        coords={"lat": [18.5, 18.6], "lon": [-66.1, -66.0]},
    ).to_netcdf(path)
    with XarraySurfaceSource(path, _manifestation()) as source:
        ocean = source.sample_surface(-66.1, 18.5)
        nodata = source.sample_surface(-66.0, 18.5)
        outside = source.sample_surface(-67.0, 18.5)
    assert ocean.value_m == -10.0
    assert ocean.surface_class.value == "OCEAN_DEPTH"
    assert ocean.spatial_state is SpatialState.FULLY_WITHIN
    assert nodata.value_m is None and nodata.spatial_state is SpatialState.NULL_EMPTY
    assert outside.value_m is None and outside.spatial_state is SpatialState.OUTSIDE
