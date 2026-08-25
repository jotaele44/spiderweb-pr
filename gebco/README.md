# gebco

Bathymetry / DEM access and marine spatial-evidence controls for the Puerto Rico region.

## What's here
- `io.py` — open and subset GEBCO NetCDF grids (`open_gebco`, `subset_region`).
- `terrain.py` — terrain-context classification over the elevation grid.
- `marine_evidence.py` — source-agnostic marine sensor lineage, coverage,
  vertical-reference, feature-evidence, artifact and temporal-comparison gates.

The pipeline-facing marine adapter is `pipeline/marine_analysis.py`.  It leaves
the established five-value `pipeline.terrain_hook` contract unchanged.

## Install
This subsystem needs the heavy scientific stack — install the extra:

```bash
pip install -e ".[gebco]"
```

(`scipy`, `xarray`, `netCDF4`, `scikit-image`.)

## Tests
`tests/test_io.py` and `tests/test_terrain.py` cover the GEBCO grid/terrain
package in the dedicated **`test-gebco`** CI job.  The marine evidence and
pipeline integration gates are covered by `tests/test_marine_evidence.py` and
`tests/test_marine_analysis.py` in the normal test matrix.

## Related docs
- Marine evidence workflow: [`docs/MARINE_SPATIAL_ANALYSIS.md`](../docs/MARINE_SPATIAL_ANALYSIS.md).
- DEM workflow docs live under [`docs/PR_DEM_*`](../docs).
- The terrain-context *contract* used by the pipeline is the stub
  `pipeline/terrain_hook.py`; the real DEM-backed implementation plugs in here.
