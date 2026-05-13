"""GEBCO 2023 NetCDF-4 I/O helpers.

Design notes
------------
* GEBCO 2023 stores a single ``elevation`` (int16) variable on ``lat`` / ``lon``
  dimensions in ascending order (south→north, west→east).
* On-disk dtype is int16 — literal metres, no scale_factor/add_offset.
* A regional subset of ~500×1100 cells occupies ~1 MB; no Dask chunking needed.
* The primary footgun is xarray's *silent empty result* when a slice direction
  mismatches coordinate order (xarray issue #1613). We guard with ``sortby``.
"""

from __future__ import annotations

import xarray as xr


def open_gebco(path: str, engine: str = "netcdf4") -> xr.Dataset:
    """Open a GEBCO 2023 NetCDF-4 file as a lazy xarray Dataset.

    Parameters
    ----------
    path:
        Path to ``GEBCO_2023.nc`` (or compatible GEBCO file).
    engine:
        Backend engine passed to :func:`xarray.open_dataset`.  ``"netcdf4"``
        (default) and ``"h5netcdf"`` both work; ``h5netcdf`` may be marginally
        faster and is better for concurrent access patterns.

    Returns
    -------
    xr.Dataset
        Lazy dataset with ``elevation`` (int16) on ``lat`` / ``lon`` coords.
        Latitude is guaranteed to be in *ascending* order.

    Raises
    ------
    ValueError
        If the ``elevation`` variable is absent — e.g., a re-gridded product
        that uses a different variable name such as ``z`` or ``Band1``.

    Notes
    -----
    Do **not** pass ``chunks=`` here; subsetting with ``.sel()`` and ``.load()``
    triggers a fast HDF5 hyperslab read that is cheaper than Dask scheduling for
    regions up to ~100 MB.
    """
    ds = xr.open_dataset(path, engine=engine)

    if "elevation" not in ds:
        raise ValueError(
            f"'elevation' variable not found in {path}. "
            "Check that this is a GEBCO 2020+ file (not an older GEBCO product "
            "that uses 'z' or 'Band1')."
        )

    # Guard against descending-latitude files (older GEBCO formats, re-gridded
    # products).  sortby is lazy — no data is loaded at this point.
    if float(ds.lat.values[0]) > float(ds.lat.values[-1]):
        ds = ds.sortby("lat")

    return ds


def subset_region(
    ds: xr.Dataset,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
) -> xr.DataArray:
    """Extract a regional bathymetry subset and load it into memory.

    Parameters
    ----------
    ds:
        Dataset returned by :func:`open_gebco` (or any similarly structured
        GEBCO-like dataset with an ``elevation`` variable).
    lat_min, lat_max:
        Latitude bounds (degrees north, −90 to +90).  Both bounds are
        **inclusive** — xarray's slice semantics.
    lon_min, lon_max:
        Longitude bounds (degrees east, −180 to +180).

    Returns
    -------
    xr.DataArray
        Loaded ``elevation`` subset, dtype int16, dimensions ``(lat, lon)``.

    Raises
    ------
    ValueError
        If the resulting subset is empty (mis-specified bounds, or bounds
        outside the file's coverage).

    Notes
    -----
    *Do not* combine ``method='nearest'`` with ``slice()``; that form of
    ``.sel()`` only accepts scalar point lookups.  Use plain ``slice()`` for
    range selection and ``method='nearest'`` only for scalar queries.
    """
    if lat_min >= lat_max:
        raise ValueError(f"lat_min ({lat_min}) must be less than lat_max ({lat_max})")
    if lon_min >= lon_max:
        raise ValueError(f"lon_min ({lon_min}) must be less than lon_max ({lon_max})")

    subset = ds["elevation"].sel(
        lat=slice(lat_min, lat_max),
        lon=slice(lon_min, lon_max),
    )

    if subset.size == 0:
        raise ValueError(
            f"Empty subset for bounds lat=[{lat_min}, {lat_max}], "
            f"lon=[{lon_min}, {lon_max}]. "
            "Verify that the bounds lie within the file's coverage and that "
            "lat_min < lat_max (GEBCO latitudes are ascending south→north)."
        )

    return subset.load()
