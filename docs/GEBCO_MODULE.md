# GEBCO Bathymetry Module

The `gebco` package provides I/O helpers and terrain-derivative computations for the GEBCO 2023 global 15 arc-second bathymetry grid, scoped to the Puerto Rico region.

---

## Purpose

The module loads GEBCO 2023 NetCDF-4 files, extracts regional subsets covering Puerto Rico and surrounding waters (including Mona Passage and the Puerto Rico Trench), and computes seafloor terrain derivatives (slope, curvature, roughness, rugosity) used by downstream GIS and mission-inference pipelines.

---

## Data source and coordinate conventions

- **Source**: GEBCO 2023 global 15 arc-second grid (`GEBCO_2023.nc`)
- **CRS**: Geographic coordinates, EPSG:4326 (WGS 84 latitude/longitude)
- **Horizontal resolution**: 15 arc-seconds (~460 m at the equator, ~420 m at 18° N)
- **Variable**: `elevation` (int16), stored in metres as literal integer values — no `scale_factor` or `add_offset` attributes
- **Latitude order**: ascending south-to-north; the module sorts descending-latitude files automatically
- **Depth sign convention**: negative values indicate depth below sea level (e.g., `-8,376` m = Puerto Rico Trench floor); positive values indicate land elevation above sea level

### Puerto Rico region reference bounds

| Area | lat_min | lat_max | lon_min | lon_max |
|------|---------|---------|---------|---------|
| Full island + shelf | 17.5 | 18.8 | -68.0 | -65.2 |
| Mona Passage | 17.8 | 18.6 | -68.0 | -67.0 |
| Puerto Rico Trench | 18.8 | 20.0 | -68.5 | -64.5 |

---

## Environment variable

| Variable | Purpose |
|----------|---------|
| `GEBCO_DATA_DIR` | Optional base directory for GEBCO NetCDF files. When set, callers can construct the path as `os.path.join(os.environ["GEBCO_DATA_DIR"], "GEBCO_2023.nc")` instead of hard-coding absolute paths. |

---

## Public API

### `gebco.io` — file I/O

#### `open_gebco(path, engine="netcdf4") -> xr.Dataset`

Opens a GEBCO 2023 NetCDF-4 file as a lazy xarray Dataset.

```python
import gebco
ds = gebco.open_gebco("/data/GEBCO_2023.nc")
# ds["elevation"] is int16, dims (lat, lon)
```

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `path` | `str` | Path to `GEBCO_2023.nc` or compatible GEBCO file |
| `engine` | `str` | xarray backend: `"netcdf4"` (default) or `"h5netcdf"` |

**Returns** `xr.Dataset` with `elevation` (int16) on ascending `lat` / `lon` coordinates.

**Raises** `ValueError` if the `elevation` variable is absent (e.g., re-gridded products that use `z` or `Band1`).

**Note**: Do not pass `chunks=` — subsetting with `.sel()` and `.load()` triggers a faster HDF5 hyperslab read for regions up to ~100 MB.

---

#### `subset_region(ds, lat_min, lat_max, lon_min, lon_max) -> xr.DataArray`

Extracts a regional bathymetry subset and loads it into memory.

```python
elev = gebco.subset_region(ds, lat_min=17.5, lat_max=18.8, lon_min=-68.0, lon_max=-65.2)
# elev.values is a (rows, cols) int16 NumPy array
# negative = underwater, positive = land
```

**Parameters**

| Name | Type | Description |
|------|------|-------------|
| `ds` | `xr.Dataset` | Dataset from `open_gebco()` |
| `lat_min` | `float` | Southern boundary (degrees north, −90 to +90) |
| `lat_max` | `float` | Northern boundary |
| `lon_min` | `float` | Western boundary (degrees east, −180 to +180) |
| `lon_max` | `float` | Eastern boundary |

Both bounds are **inclusive** (xarray slice semantics). `lat_min` must be strictly less than `lat_max`; same for `lon_min` / `lon_max`.

**Returns** Loaded `xr.DataArray`, dtype int16, dimensions `(lat, lon)`.

**Raises** `ValueError` for inverted bounds or an empty result (bounds outside file coverage).

---

#### `validate_bounds(lat_min, lat_max, lon_min, lon_max)`

Validates that a bounding box is well-formed and lies within GEBCO global coverage before passing it to `subset_region()`. Raises `ValueError` with a descriptive message for any of the following:

- `lat_min >= lat_max` or `lon_min >= lon_max`
- Latitude values outside [−90, 90]
- Longitude values outside [−180, 180]

---

### `gebco.terrain` — derivative computations

All functions accept a 2-D NumPy array (or xarray DataArray) of elevation values in metres. They return float64 arrays of the same shape. NaN values (land mask) are handled via weight-normalised convolution with one-pixel dilation to flag unreliable edge cells.

#### `cell_size_meters(lat_deg, res_arcsec=15.0) -> (dx, dy)`

Returns east–west (`dx`) and north–south (`dy`) cell sizes in metres for a given latitude. `dx` shrinks toward the poles; `dy` is approximately constant (~463 m for 15 arc-second resolution).

```python
from gebco.terrain import cell_size_meters
dx, dy = cell_size_meters(lat_deg=18.2)   # centre of Puerto Rico
```

#### `compute_slope(dem, dx, dy) -> (slope_deg, dz_dx, dz_dy)`

Horn (1981) slope in degrees using a 3×3 weighted Sobel kernel. Returns slope angle (0 = flat, 90 = vertical), plus east–west and north–south partial derivatives.

#### `compute_curvatures(dem, dx, dy) -> (profile, plan, general)`

Zevenbergen & Thorne (1987) curvatures. Profile curvature is in the direction of steepest descent (negative = concave-up); plan curvature is perpendicular (negative = converging flow); general curvature is the Laplacian `−(zxx + zyy)`.

#### `compute_roughness(dem, window=3) -> np.ndarray`

Moving-window elevation standard deviation using the O(N) variance identity with `scipy.ndimage.uniform_filter`. `window` must be an odd integer ≥ 3.

#### `compute_rugosity(dem, dx, dy, method="area_ratio", window=3) -> np.ndarray`

Seafloor rugosity via one of two metrics:

| `method` | Formula | Notes |
|----------|---------|-------|
| `"area_ratio"` | `sqrt(1 + dz_dx² + dz_dy²)` | Fast, single-pass; equals 1 on flat terrain |
| `"vrm"` | Sappington et al. (2007) VRM | Decouples ruggedness from mean slope; preferred for habitat analysis |

---

## `TerrainAnalyzer` class

`TerrainAnalyzer` wraps the functional API into a stateful object that holds a loaded elevation tile and provides higher-level analytical methods targeted at Puerto Rico operational use cases.

```python
from gebco import TerrainAnalyzer

ta = TerrainAnalyzer(elevation_array, lat_center=18.2)
```

### Methods

#### `underwater_ridges(depth_threshold=-200, slope_min=5.0) -> gpd.GeoDataFrame`

Identifies contiguous underwater ridge features shallower than `depth_threshold` metres with slope exceeding `slope_min` degrees. Returns a GeoDataFrame of ridge polygon geometries with attributes `mean_depth`, `max_slope`, and `area_km2`.

#### `slope_gradient_map(percentile_clip=2) -> xr.DataArray`

Computes a Horn (1981) slope grid over the full tile with optional percentile clipping at both ends to suppress edge artefacts. Returns an xarray DataArray with `lat`/`lon` coordinates for direct plotting or export.

#### `find_landing_zones(max_slope=3.0, min_depth=-50, max_depth=-5) -> gpd.GeoDataFrame`

Identifies candidate submarine landing zones — cells where slope is below `max_slope` degrees and depth falls within [`min_depth`, `max_depth`] metres. Returns polygon GeoDataFrame sorted by area descending.

#### `mona_passage_profile(n_points=200) -> pd.DataFrame`

Extracts a bathymetric cross-section across Mona Passage (approximately 18.1° N, from −68.0° to −67.0° lon). Returns a DataFrame with columns `lon`, `depth_m`, `slope_deg`.

#### `to_xarray() -> xr.Dataset`

Exports all computed derivative grids (slope, curvature components, roughness, rugosity) as a single xarray Dataset with full coordinate metadata, ready for NetCDF export via `ds.to_netcdf()`.

---

## Standalone functions

These functions are available at the `gebco.terrain` level and do not require a `TerrainAnalyzer` instance.

### `mona_passage_profile(ds, n_points=200) -> pd.DataFrame`

Extracts a bathymetric transect across Mona Passage from a full GEBCO Dataset returned by `open_gebco()`. Equivalent to `TerrainAnalyzer.mona_passage_profile()` but operates on the raw Dataset directly.

```python
import gebco
ds = gebco.open_gebco("/data/GEBCO_2023.nc")
profile = gebco.terrain.mona_passage_profile(ds)
```

### `underwater_ridges(elevation, dx, dy, depth_threshold=-200, slope_min=5.0) -> np.ndarray`

Boolean mask of ridge cells satisfying depth and slope thresholds. The functional counterpart to `TerrainAnalyzer.underwater_ridges()` — returns a NumPy mask rather than a GeoDataFrame.

---

## Typical workflow

```python
import os
import gebco

# 1. Open the GEBCO file (path from env var or hard-coded)
nc_path = os.path.join(os.environ.get("GEBCO_DATA_DIR", "/data"), "GEBCO_2023.nc")
ds = gebco.open_gebco(nc_path)

# 2. Extract Puerto Rico region
elev = gebco.subset_region(ds, lat_min=17.5, lat_max=18.8, lon_min=-68.0, lon_max=-65.2)

# 3. Compute cell sizes at tile centre
from gebco.terrain import cell_size_meters, compute_slope, compute_roughness
dx, dy = cell_size_meters(lat_deg=18.15)

# 4. Terrain derivatives
slope, _, _ = compute_slope(elev.values, dx, dy)
roughness = compute_roughness(elev.values, window=5)

# Negative elevation = underwater; positive = land
underwater_mask = elev.values < 0
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `xarray` | NetCDF I/O and labelled arrays |
| `netcdf4` or `h5netcdf` | xarray backend engine |
| `numpy` | Array operations |
| `scipy` | `ndimage.correlate`, `uniform_filter` for terrain kernels |

Install GEBCO-only dependencies:

```bash
pip install -r requirements-gebco.txt
```
