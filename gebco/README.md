# gebco

Bathymetry / DEM access for the Puerto Rico region.

## What's here
- `io.py` — open and subset GEBCO NetCDF grids (`open_gebco`, `subset_region`).
- `terrain.py` — terrain-context classification over the elevation grid.

## Install
This subsystem needs the heavy scientific stack — install the extra:

```bash
pip install -e ".[gebco]"
```

(`scipy`, `xarray`, `netCDF4`, `scikit-image`.)

## Tests
`tests/test_io.py` and `tests/test_terrain.py` cover this package and run in the
dedicated **`test-gebco`** CI job (they are excluded from the base test job
because the gebco extra isn't installed there — see `.github/workflows/ci.yml`).

## Related docs
- DEM workflow docs live under [`docs/PR_DEM_*`](../docs).
- The terrain-context *contract* used by the pipeline is the stub
  `pipeline/terrain_hook.py`; the real DEM-backed implementation plugs in here.
