"""Lazy source-native NetCDF adapter for the unified Spiderweb surface API."""
from __future__ import annotations

import math
from pathlib import Path

from .surface_analysis import SpatialState
from .surface_engine import SurfaceManifestation, SurfaceSample, RegularSurfaceGrid


class XarraySurfaceSource:
    def __init__(self, path: str | Path, manifestation: SurfaceManifestation, *, variable: str = "Band1", lat_name: str = "lat", lon_name: str = "lon"):
        import xarray as xr
        self.path = Path(path); self.manifestation = manifestation
        self.dataset = xr.open_dataset(self.path, engine="netcdf4")
        if variable not in self.dataset or lat_name not in self.dataset.coords or lon_name not in self.dataset.coords:
            raise ValueError("source schema does not contain declared surface/coordinate variables")
        self.variable, self.lat_name, self.lon_name = variable, lat_name, lon_name

    def close(self): self.dataset.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def sample_surface(self, lon: float, lat: float) -> SurfaceSample:
        xs=self.dataset[self.lon_name]; ys=self.dataset[self.lat_name]
        common=dict(lon=float(lon),lat=float(lat),source_manifestation_id=self.manifestation.manifestation_id,measurement_class=self.manifestation.measurement_class,vertical_datum=self.manifestation.vertical_datum)
        if lon < float(xs.min()) or lon > float(xs.max()) or lat < float(ys.min()) or lat > float(ys.max()):
            return SurfaceSample(value_m=None,surface_class=None,slope_deg=None,aspect_deg=None,spatial_state=SpatialState.OUTSIDE,**common)
        raw=self.dataset[self.variable].sel({self.lon_name:lon,self.lat_name:lat},method="nearest").values
        value=float(raw)
        if not math.isfinite(value):
            return SurfaceSample(value_m=None,surface_class=None,slope_deg=None,aspect_deg=None,spatial_state=SpatialState.NULL_EMPTY,**common)
        return SurfaceSample(value_m=value,surface_class=RegularSurfaceGrid._surface_class(value),slope_deg=None,aspect_deg=None,spatial_state=SpatialState.FULLY_WITHIN,**common)
