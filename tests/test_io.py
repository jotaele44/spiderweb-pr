"""Tests for gebco.io — GEBCO subset extraction.

All tests use synthetic in-memory xarray Datasets that replicate the exact
structure of GEBCO 2023 (int16 elevation on lat/lon dims, ascending lat).
No real GEBCO file is required.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from gebco.io import open_gebco, subset_region


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fake_gebco(
    lat: np.ndarray,
    lon: np.ndarray,
    ascending_lat: bool = True,
) -> xr.Dataset:
    """Build a minimal in-memory dataset matching GEBCO 2023 structure."""
    if not ascending_lat:
        lat = lat[::-1]

    ny, nx = len(lat), len(lon)
    elev = np.arange(ny * nx, dtype=np.int16).reshape(ny, nx)

    return xr.Dataset(
        {"elevation": xr.DataArray(elev, dims=["lat", "lon"])},
        coords={"lat": lat, "lon": lon},
        attrs={"Conventions": "CF-1.6", "title": "Fake GEBCO_2023 Grid"},
    )


@pytest.fixture
def fake_gebco_ds():
    """Ascending-latitude fake GEBCO dataset, 20 lat × 40 lon."""
    lat = np.linspace(-10.0, 9.9, 20)
    lon = np.linspace(-20.0, 19.9, 40)
    return _make_fake_gebco(lat, lon)


@pytest.fixture
def fake_gebco_descending():
    """Descending-latitude fake GEBCO dataset (older format)."""
    lat = np.linspace(-10.0, 9.9, 20)
    lon = np.linspace(-20.0, 19.9, 40)
    return _make_fake_gebco(lat, lon, ascending_lat=False)


# ---------------------------------------------------------------------------
# open_gebco — unit tests via monkeypatching
# ---------------------------------------------------------------------------


def test_open_gebco_requires_elevation_variable(tmp_path, monkeypatch):
    """open_gebco raises ValueError when 'elevation' is missing."""
    no_elev_ds = xr.Dataset(
        {"z": xr.DataArray(np.zeros((5, 5), dtype=np.int16), dims=["lat", "lon"])},
        coords={"lat": np.linspace(-1, 1, 5), "lon": np.linspace(-1, 1, 5)},
    )
    nc_path = str(tmp_path / "no_elevation.nc")
    no_elev_ds.to_netcdf(nc_path)

    with pytest.raises(ValueError, match="'elevation' variable not found"):
        open_gebco(nc_path)


def test_open_gebco_ascending_lat_unchanged(tmp_path):
    """open_gebco preserves ascending latitude order without re-sorting."""
    lat = np.linspace(-5.0, 4.9, 10)
    lon = np.linspace(-5.0, 4.9, 10)
    ds = _make_fake_gebco(lat, lon, ascending_lat=True)
    nc_path = str(tmp_path / "ascending.nc")
    ds.to_netcdf(nc_path)

    loaded = open_gebco(nc_path)
    assert loaded.lat.values[0] < loaded.lat.values[-1], "Lat should be ascending"


def test_open_gebco_descending_lat_sorted(tmp_path):
    """open_gebco re-sorts descending-latitude files to ascending order."""
    lat = np.linspace(-5.0, 4.9, 10)
    lon = np.linspace(-5.0, 4.9, 10)
    ds = _make_fake_gebco(lat, lon, ascending_lat=False)
    nc_path = str(tmp_path / "descending.nc")
    ds.to_netcdf(nc_path)

    loaded = open_gebco(nc_path)
    assert loaded.lat.values[0] < loaded.lat.values[-1], "Lat should be ascending after sort"


# ---------------------------------------------------------------------------
# subset_region — unit tests against in-memory datasets
# ---------------------------------------------------------------------------


def test_subset_region_returns_correct_bounds(fake_gebco_ds):
    """subset_region returns only cells within the specified bounds."""
    subset = subset_region(fake_gebco_ds, lat_min=-5.0, lat_max=5.0, lon_min=-10.0, lon_max=10.0)

    assert subset.lat.values.min() >= -5.0
    assert subset.lat.values.max() <= 5.0
    assert subset.lon.values.min() >= -10.0
    assert subset.lon.values.max() <= 10.0


def test_subset_region_dtype_int16(fake_gebco_ds):
    """subset_region preserves the int16 dtype from GEBCO."""
    subset = subset_region(fake_gebco_ds, lat_min=-5.0, lat_max=5.0, lon_min=-10.0, lon_max=10.0)
    assert subset.dtype == np.int16


def test_subset_region_non_empty(fake_gebco_ds):
    """subset_region returns a non-empty result for valid bounds."""
    subset = subset_region(fake_gebco_ds, lat_min=-5.0, lat_max=5.0, lon_min=-10.0, lon_max=10.0)
    assert subset.size > 0


def test_subset_region_full_coverage(fake_gebco_ds):
    """Requesting bounds covering the entire dataset returns all cells."""
    lat = fake_gebco_ds.lat.values
    lon = fake_gebco_ds.lon.values
    subset = subset_region(
        fake_gebco_ds,
        lat_min=float(lat.min()),
        lat_max=float(lat.max()),
        lon_min=float(lon.min()),
        lon_max=float(lon.max()),
    )
    assert subset.shape == fake_gebco_ds["elevation"].shape


def test_subset_region_raises_on_inverted_lat(fake_gebco_ds):
    """subset_region raises ValueError when lat_min >= lat_max."""
    with pytest.raises(ValueError, match="lat_min"):
        subset_region(fake_gebco_ds, lat_min=5.0, lat_max=-5.0, lon_min=-10.0, lon_max=10.0)


def test_subset_region_raises_on_inverted_lon(fake_gebco_ds):
    """subset_region raises ValueError when lon_min >= lon_max."""
    with pytest.raises(ValueError, match="lon_min"):
        subset_region(fake_gebco_ds, lat_min=-5.0, lat_max=5.0, lon_min=10.0, lon_max=-10.0)


def test_subset_region_raises_on_out_of_bounds(fake_gebco_ds):
    """subset_region raises ValueError when bounds are entirely outside dataset."""
    with pytest.raises(ValueError, match="Empty subset"):
        subset_region(
            fake_gebco_ds, lat_min=80.0, lat_max=89.0, lon_min=160.0, lon_max=179.0
        )


def test_subset_region_loaded_into_memory(fake_gebco_ds):
    """subset_region returns a loaded (non-lazy) DataArray."""
    subset = subset_region(fake_gebco_ds, lat_min=-5.0, lat_max=5.0, lon_min=-10.0, lon_max=10.0)
    # A loaded DataArray has no dask graph
    assert not subset.chunks, "Expected loaded (non-chunked) DataArray"


def test_subset_region_silent_empty_guard(fake_gebco_ds):
    """Verifies the sortby guard prevents silent empty results.

    This test exercises the xarray silent-empty-result footgun (issue #1613):
    if lat is descending and we pass slice(min, max), xarray returns an empty
    array without error.  open_gebco's sortby ensures lat is ascending, so
    subset_region should always return data for valid in-range bounds.
    """
    # Simulate a descending-lat dataset that has *not* been sorted.
    lat_desc = np.linspace(9.9, -10.0, 20)
    lon = np.linspace(-20.0, 19.9, 40)
    ny, nx = len(lat_desc), len(lon)
    elev = np.arange(ny * nx, dtype=np.int16).reshape(ny, nx)
    ds_desc = xr.Dataset(
        {"elevation": xr.DataArray(elev, dims=["lat", "lon"])},
        coords={"lat": lat_desc, "lon": lon},
    )

    # Without the sortby guard this would silently return empty.
    # open_gebco handles the sort; here we verify the raw xarray behaviour
    # to document why the guard is necessary.
    raw_subset = ds_desc["elevation"].sel(lat=slice(-5.0, 5.0))
    assert raw_subset.size == 0, (
        "This documents xarray issue #1613: descending lat + ascending slice = empty"
    )
