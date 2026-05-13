"""Terrain-derivative computations for GEBCO bathymetry grids.

All functions accept a 2-D NumPy array (or xarray DataArray) of elevation
values (metres, int16 or float64) together with horizontal cell sizes in
metres. They return float64 arrays of the same shape.

Algorithms
----------
* **Slope** — Horn (1981) 3×3 weighted Sobel kernel (GIS industry standard,
  used by GDAL, ArcGIS, GRASS).
* **Curvature** — Zevenbergen & Thorne (1987) second-derivative formulation
  yielding profile, plan, and general (Laplacian) curvatures.
* **Roughness** — Moving-window standard deviation via the variance identity
  with ``scipy.ndimage.uniform_filter`` (O(N) regardless of window size,
  ~100× faster than ``generic_filter``).
* **Rugosity** — Two metrics:
    - Gradient-based surface-area ratio (fast): sqrt(1 + dz_dx² + dz_dy²).
    - Vector Ruggedness Measure (Sappington et al. 2007): normal-vector
      dispersion in a moving window.

NaN handling
------------
GEBCO itself has no NaN values, but callers may mask land pixels before
passing bathymetry-only arrays. All derivative functions detect NaN, fill
with zero for convolution, normalise by a congruent weight map, and restore
NaN at masked locations (plus a one-pixel dilation to flag unreliable edges).
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------


def cell_size_meters(
    lat_deg: float | np.ndarray,
    res_arcsec: float = 15.0,
) -> tuple[float | np.ndarray, float]:
    """Return (dx, dy) cell sizes in metres for a given latitude.

    Parameters
    ----------
    lat_deg:
        Latitude in decimal degrees (scalar or 1-D array for per-row dx).
    res_arcsec:
        Grid spacing in arc-seconds (15 for GEBCO 2023).

    Returns
    -------
    dx : float | np.ndarray
        East–west cell size(s) in metres.  Shrinks toward the poles.
    dy : float
        North–south cell size in metres (~constant everywhere).

    Notes
    -----
    For a small regional tile (e.g., 5° latitude span) computing ``dx`` at
    the tile's centre latitude is acceptable.  For large or high-latitude
    domains, pass a 1-D latitude array and broadcast the returned ``dx`` over
    rows when calling derivative functions.
    """
    res_deg = res_arcsec / 3600.0
    dy = res_deg * 111_320.0
    dx = res_deg * 111_320.0 * np.cos(np.radians(lat_deg))
    return dx, dy


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_float64(arr: np.ndarray) -> np.ndarray:
    """Return arr as float64, preserving shape; treats int16 GEBCO values."""
    return arr.astype(np.float64, copy=False)


def _nan_convolve(
    data: np.ndarray,
    kernel: np.ndarray,
) -> np.ndarray:
    """Cross-correlate *data* with *kernel*, handling NaN via weight normalisation.

    Uses ``scipy.ndimage.correlate`` (no kernel flip) to match the GIS
    convention used by Horn (1981) and Zevenbergen & Thorne (1987), where
    kernels are written in the natural orientation (right column = east
    neighbour for the x-derivative).  ``ndimage.convolve`` flips the kernel,
    which negates antisymmetric gradient kernels.

    Replaces NaN with 0, correlates data and a binary valid-pixel map with the
    same kernel, then divides to normalise.  One-pixel dilation of the NaN
    mask is applied to the output to flag cells whose neighbourhood contained
    any invalid input pixel.

    Parameters
    ----------
    data:
        2-D float64 array possibly containing NaN.
    kernel:
        Correlation kernel (no NaN).

    Returns
    -------
    np.ndarray
        Correlated array with NaN at originally-masked pixels and their
        immediate 8-connected neighbours.
    """
    nan_mask = np.isnan(data)
    if not nan_mask.any():
        return ndimage.correlate(data, kernel, mode="nearest")

    filled = np.where(nan_mask, 0.0, data)
    valid = (~nan_mask).astype(np.float64)

    result = ndimage.correlate(filled, kernel, mode="nearest")
    weight = ndimage.correlate(valid, np.abs(kernel), mode="nearest")

    kernel_sum = np.abs(kernel).sum()
    result = np.where(weight > 0, result / weight * kernel_sum, np.nan)

    # Dilate NaN mask by one pixel to flag unreliable edge cells.
    dilated = ndimage.binary_dilation(nan_mask)
    result[dilated] = np.nan
    return result


# ---------------------------------------------------------------------------
# Slope (Horn 1981)
# ---------------------------------------------------------------------------


def compute_slope(
    dem: np.ndarray,
    dx: float,
    dy: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Horn (1981) slope in degrees plus raw partial derivatives.

    Uses the GIS-standard 3×3 weighted Sobel kernel that incorporates six
    neighbours per derivative, giving better noise resistance than
    ``numpy.gradient``'s simple two-point central difference.

    Parameters
    ----------
    dem:
        2-D elevation array (metres).  May contain NaN (land mask).
    dx:
        East–west cell size in metres (use :func:`cell_size_meters`).
    dy:
        North–south cell size in metres.

    Returns
    -------
    slope_deg : np.ndarray
        Slope angle in degrees (0 = flat, 90 = vertical cliff).
    dz_dx : np.ndarray
        East–west partial derivative (dimensionless rise/run).
    dz_dy : np.ndarray
        North–south partial derivative (dimensionless rise/run).
    """
    dem = _to_float64(dem)

    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64) / (8.0 * dx)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float64) / (8.0 * dy)

    dz_dx = _nan_convolve(dem, kx)
    dz_dy = _nan_convolve(dem, ky)
    slope_deg = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))

    return slope_deg, dz_dx, dz_dy


# ---------------------------------------------------------------------------
# Curvature (Zevenbergen & Thorne 1987)
# ---------------------------------------------------------------------------


def compute_curvatures(
    dem: np.ndarray,
    dx: float,
    dy: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zevenbergen & Thorne (1987) profile, plan, and general curvatures.

    Parameters
    ----------
    dem:
        2-D elevation array (metres).  May contain NaN.
    dx:
        East–west cell size in metres.
    dy:
        North–south cell size in metres.

    Returns
    -------
    profile : np.ndarray
        Profile curvature (in direction of steepest descent).  Negative =
        concave-up (accelerating flow); positive = convex-up.
    plan : np.ndarray
        Plan curvature (perpendicular to steepest descent).  Negative =
        converging flow; positive = diverging.
    general : np.ndarray
        General (Laplacian) curvature = -(zxx + zyy).
    """
    dem = _to_float64(dem)

    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64) / (8.0 * dx)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float64) / (8.0 * dy)
    kxx = np.array([[0, 0, 0], [1, -2, 1], [0, 0, 0]], dtype=np.float64) / (dx**2)
    kyy = np.array([[0, 1, 0], [0, -2, 0], [0, 1, 0]], dtype=np.float64) / (dy**2)
    kxy = np.array([[1, 0, -1], [0, 0, 0], [-1, 0, 1]], dtype=np.float64) / (4.0 * dx * dy)

    zx = _nan_convolve(dem, kx)
    zy = _nan_convolve(dem, ky)
    zxx = _nan_convolve(dem, kxx)
    zyy = _nan_convolve(dem, kyy)
    zxy = _nan_convolve(dem, kxy)

    p = zx**2 + zy**2
    q = p + 1.0
    # Use a safe denominator (p_safe > 0 everywhere) to avoid division-by-zero
    # RuntimeWarning inside np.where; the np.where mask zeros flat cells.
    p_safe = np.where(p > 0, p, 1.0)

    profile = np.where(
        p > 0,
        -(zxx * zx**2 + 2.0 * zxy * zx * zy + zyy * zy**2) / (p_safe * q**1.5),
        0.0,
    )
    plan = np.where(
        p > 0,
        -(zxx * zy**2 - 2.0 * zxy * zx * zy + zyy * zx**2) / (p_safe**1.5),
        0.0,
    )
    general = -(zxx + zyy)

    return profile, plan, general


# ---------------------------------------------------------------------------
# Roughness — windowed standard deviation
# ---------------------------------------------------------------------------


def compute_roughness(dem: np.ndarray, window: int = 3) -> np.ndarray:
    """Moving-window standard deviation of elevation.

    Uses the variance identity ``Var(X) = E[X²] − E[X]²`` with
    ``scipy.ndimage.uniform_filter``, which runs in O(N) time regardless of
    window size (separable running-sum algorithm, ~100× faster than
    ``generic_filter``).

    Parameters
    ----------
    dem:
        2-D elevation array (metres).  NaN values are excluded from statistics.
    window:
        Side length of the square moving window (must be odd and ≥ 3).

    Returns
    -------
    np.ndarray
        Per-cell elevation standard deviation.  0 on perfectly flat terrain.
        NaN where the centre cell was NaN.
    """
    if window < 3 or window % 2 == 0:
        raise ValueError(f"window must be an odd integer ≥ 3, got {window}")

    dem = _to_float64(dem)
    nan_mask = np.isnan(dem)

    if nan_mask.any():
        filled = np.where(nan_mask, 0.0, dem)
        valid = (~nan_mask).astype(np.float64)

        mean = ndimage.uniform_filter(filled, size=window, mode="nearest")
        mean_sq = ndimage.uniform_filter(filled**2, size=window, mode="nearest")
        count = ndimage.uniform_filter(valid, size=window, mode="nearest") * window**2

        # Correct mean for the zero-fill: mean_true = sum / count
        sum_ = ndimage.uniform_filter(filled, size=window, mode="nearest") * window**2
        sum_sq = (
            ndimage.uniform_filter(filled**2, size=window, mode="nearest") * window**2
        )

        variance = np.where(
            count > 1,
            (sum_sq - sum_**2 / count) / (count - 1),
            0.0,
        )
        roughness = np.sqrt(np.maximum(variance, 0.0))
        roughness[nan_mask] = np.nan
        return roughness

    mean = ndimage.uniform_filter(dem, size=window, mode="nearest")
    mean_sq = ndimage.uniform_filter(dem**2, size=window, mode="nearest")
    return np.sqrt(np.maximum(mean_sq - mean**2, 0.0))


# ---------------------------------------------------------------------------
# Rugosity
# ---------------------------------------------------------------------------


def compute_rugosity(
    dem: np.ndarray,
    dx: float,
    dy: float,
    method: str = "area_ratio",
    window: int = 3,
) -> np.ndarray:
    """Compute seafloor rugosity using one of two standard metrics.

    Parameters
    ----------
    dem:
        2-D elevation array (metres).  May contain NaN.
    dx:
        East–west cell size in metres.
    dy:
        North–south cell size in metres.
    method:
        ``"area_ratio"`` (default) — gradient-based surface-area ratio:
        ``sqrt(1 + dz_dx² + dz_dy²)``.  Equals 1 on flat terrain, increases
        with relief.  Fast; single-pass computation.

        ``"vrm"`` — Vector Ruggedness Measure (Sappington et al. 2007).
        Decomposes surface normals into 3-D unit vectors and measures their
        dispersion within a moving window via ``uniform_filter``.  Ranges from
        0 (flat) to 1 (maximally rugged).  Preferred for ecological habitat
        analysis because it decouples ruggedness from mean slope.
    window:
        Moving-window size for ``"vrm"`` (ignored for ``"area_ratio"``).
        Must be an odd integer ≥ 3.

    Returns
    -------
    np.ndarray
        Rugosity values; shape matches *dem*.

    Raises
    ------
    ValueError
        If *method* is not one of the supported options.
    """
    dem = _to_float64(dem)
    _, dz_dx, dz_dy = compute_slope(dem, dx, dy)

    if method == "area_ratio":
        return np.sqrt(1.0 + dz_dx**2 + dz_dy**2)

    if method == "vrm":
        if window < 3 or window % 2 == 0:
            raise ValueError(f"window must be an odd integer ≥ 3, got {window}")

        # Surface normal magnitude: sqrt(dz_dx² + dz_dy² + 1)  (always > 0)
        norm_mag = np.sqrt(dz_dx**2 + dz_dy**2 + 1.0)

        # Unit-normal components
        nx = -dz_dx / norm_mag
        ny = -dz_dy / norm_mag
        nz = 1.0 / norm_mag

        # Sum unit normals in moving window
        sum_nx = ndimage.uniform_filter(nx, size=window, mode="nearest") * window**2
        sum_ny = ndimage.uniform_filter(ny, size=window, mode="nearest") * window**2
        sum_nz = ndimage.uniform_filter(nz, size=window, mode="nearest") * window**2

        resultant = np.sqrt(sum_nx**2 + sum_ny**2 + sum_nz**2)
        n_cells = float(window**2)

        # VRM = 1 - (resultant / n_cells); 0 = flat, 1 = maximally rugged
        vrm = 1.0 - resultant / n_cells
        return np.clip(vrm, 0.0, 1.0)

    raise ValueError(f"Unknown rugosity method '{method}'. Use 'area_ratio' or 'vrm'.")
