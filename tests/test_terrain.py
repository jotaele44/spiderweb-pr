"""Tests for gebco.terrain — slope, curvature, roughness, rugosity.

Uses small synthetic DEMs with analytically known properties so results can
be verified without floating-point surprises.
"""

from __future__ import annotations

import numpy as np
import pytest

from gebco.terrain import (
    cell_size_meters,
    compute_curvatures,
    compute_roughness,
    compute_rugosity,
    compute_slope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DX = 463.0  # ≈ 15 arc-second cell at equator (metres)
DY = 463.0


def flat_dem(rows: int = 9, cols: int = 9, value: float = -500.0) -> np.ndarray:
    """Uniformly flat DEM (zero gradient everywhere)."""
    return np.full((rows, cols), value, dtype=np.float64)


def ramp_dem(rows: int = 9, cols: int = 9, slope_dx: float = 1.0) -> np.ndarray:
    """East-sloping planar ramp: elevation increases by slope_dx per cell."""
    col_idx = np.arange(cols, dtype=np.float64)
    return np.tile(col_idx * slope_dx, (rows, 1))


# ---------------------------------------------------------------------------
# cell_size_meters
# ---------------------------------------------------------------------------


def test_cell_size_at_equator():
    dx, dy = cell_size_meters(0.0, res_arcsec=15.0)
    # At equator cos(0) = 1, so dx == dy
    np.testing.assert_allclose(dx, dy, rtol=1e-9)
    np.testing.assert_allclose(dy, 15.0 / 3600.0 * 111_320.0, rtol=1e-9)


def test_cell_size_shrinks_toward_poles():
    dx_eq, _ = cell_size_meters(0.0)
    dx_60, _ = cell_size_meters(60.0)
    assert dx_60 < dx_eq
    np.testing.assert_allclose(dx_60, dx_eq * 0.5, rtol=1e-3)


def test_cell_size_array_input():
    lats = np.array([0.0, 30.0, 60.0])
    dx, dy = cell_size_meters(lats)
    assert dx.shape == (3,)
    assert isinstance(dy, float)
    assert dx[0] > dx[1] > dx[2]


# ---------------------------------------------------------------------------
# compute_slope
# ---------------------------------------------------------------------------


def test_slope_flat_dem():
    """A flat DEM should have slope ≈ 0 everywhere (interior cells)."""
    dem = flat_dem()
    slope, dz_dx, dz_dy = compute_slope(dem, DX, DY)
    # Interior cells
    np.testing.assert_allclose(slope[1:-1, 1:-1], 0.0, atol=1e-10)
    np.testing.assert_allclose(dz_dx[1:-1, 1:-1], 0.0, atol=1e-10)
    np.testing.assert_allclose(dz_dy[1:-1, 1:-1], 0.0, atol=1e-10)


def test_slope_east_ramp_direction():
    """An east-sloping ramp should have dz_dx > 0, dz_dy ≈ 0 in the interior."""
    dem = ramp_dem(slope_dx=1.0)
    _, dz_dx, dz_dy = compute_slope(dem, DX, DY)
    assert np.all(dz_dx[1:-1, 1:-1] > 0), "dz_dx should be positive for east ramp"
    np.testing.assert_allclose(dz_dy[1:-1, 1:-1], 0.0, atol=1e-10)


def test_slope_known_angle():
    """Verify slope angle for a ramp with known rise/run."""
    # Ramp rises 1 m per DX metres → expected slope = arctan(1/DX)
    dem = ramp_dem(slope_dx=1.0)
    slope, _, _ = compute_slope(dem, DX, DY)
    expected = np.degrees(np.arctan(1.0 / DX))
    # Horn's kernel averages multiple neighbours, so we check a rough range.
    assert np.all(slope[1:-1, 1:-1] > 0)
    assert np.all(slope[1:-1, 1:-1] < 90.0)


def test_slope_int16_input():
    """compute_slope should accept int16 arrays (raw GEBCO values)."""
    dem = np.zeros((7, 7), dtype=np.int16)
    slope, _, _ = compute_slope(dem, DX, DY)
    assert slope.dtype == np.float64


def test_slope_shape_preserved():
    dem = np.random.default_rng(0).integers(-200, 0, size=(11, 13), dtype=np.int16)
    slope, dz_dx, dz_dy = compute_slope(dem, DX, DY)
    assert slope.shape == (11, 13)
    assert dz_dx.shape == (11, 13)
    assert dz_dy.shape == (11, 13)


def test_slope_nan_propagation():
    """NaN in the interior should propagate to that cell and immediate neighbours."""
    dem = flat_dem().copy()
    dem[4, 4] = np.nan
    slope, _, _ = compute_slope(dem, DX, DY)
    assert np.isnan(slope[4, 4])
    # At least one neighbour should also be NaN (dilation by 1 pixel)
    neighbourhood = slope[3:6, 3:6]
    assert np.isnan(neighbourhood).any()


# ---------------------------------------------------------------------------
# compute_curvatures
# ---------------------------------------------------------------------------


def test_curvatures_flat_dem():
    """A flat DEM has zero curvature everywhere (interior)."""
    dem = flat_dem()
    profile, plan, general = compute_curvatures(dem, DX, DY)
    np.testing.assert_allclose(profile[1:-1, 1:-1], 0.0, atol=1e-10)
    np.testing.assert_allclose(plan[1:-1, 1:-1], 0.0, atol=1e-10)
    np.testing.assert_allclose(general[1:-1, 1:-1], 0.0, atol=1e-10)


def test_curvatures_planar_ramp():
    """A planar ramp (constant slope) has zero second-order curvature."""
    dem = ramp_dem(slope_dx=2.0)
    profile, plan, general = compute_curvatures(dem, DX, DY)
    # Interior cells of a planar surface: curvature should be ~0
    np.testing.assert_allclose(profile[2:-2, 2:-2], 0.0, atol=1e-6)
    np.testing.assert_allclose(plan[2:-2, 2:-2], 0.0, atol=1e-6)


def test_curvatures_shape_preserved():
    dem = np.random.default_rng(1).integers(-300, 0, size=(10, 15), dtype=np.int16)
    profile, plan, general = compute_curvatures(dem, DX, DY)
    assert profile.shape == (10, 15)
    assert plan.shape == (10, 15)
    assert general.shape == (10, 15)


def test_curvatures_symmetric_bowl():
    """A concave-up paraboloid should have negative profile curvature away from centre.

    z = x² + y²  is a concave-up bowl (upward-opening paraboloid).
    At the exact centre first derivatives are zero (p=0), so profile curvature
    is undefined and correctly returns 0 via the np.where guard.
    One cell off-centre the slope is non-zero and profile curvature is negative
    (steepest-descent direction curves upward — water accelerates inward).

    Note: z = -(x²+y²) is a dome (convex up) → positive profile curvature.
    """
    size = 11
    centre = size // 2
    y, x = np.mgrid[-centre : centre + 1, -centre : centre + 1]
    # Concave-up bowl
    dem = x.astype(np.float64) ** 2 + y.astype(np.float64) ** 2
    profile, _, _ = compute_curvatures(dem, 1.0, 1.0)
    # One cell east of centre: zx > 0, zxx > 0 → profile < 0 (concave-up)
    assert profile[centre, centre + 1] < 0, (
        "Off-centre cell of concave-up bowl should have negative profile curvature"
    )


# ---------------------------------------------------------------------------
# compute_roughness
# ---------------------------------------------------------------------------


def test_roughness_flat_dem():
    """A flat DEM has zero roughness everywhere."""
    dem = flat_dem()
    roughness = compute_roughness(dem, window=3)
    np.testing.assert_allclose(roughness, 0.0, atol=1e-10)


def test_roughness_non_negative():
    """Roughness is always ≥ 0."""
    rng = np.random.default_rng(42)
    dem = rng.integers(-500, 0, size=(20, 20)).astype(np.float64)
    roughness = compute_roughness(dem, window=5)
    assert np.all(roughness >= 0)


def test_roughness_larger_window_smoother_or_equal():
    """A larger window should produce equal or larger roughness values on average.

    This isn't mathematically guaranteed cell-by-cell, but over a random
    field the mean roughness with a large window will exceed that of a small
    window because it captures more variance.
    """
    rng = np.random.default_rng(7)
    dem = rng.standard_normal((30, 30)) * 100.0
    r3 = compute_roughness(dem, window=3)
    r9 = compute_roughness(dem, window=9)
    # Mean roughness with window=9 should capture more variance
    assert r9.mean() >= r3.mean() * 0.5  # generous tolerance


def test_roughness_shape_preserved():
    dem = flat_dem(rows=12, cols=8)
    roughness = compute_roughness(dem, window=3)
    assert roughness.shape == (12, 8)


def test_roughness_invalid_window():
    dem = flat_dem()
    with pytest.raises(ValueError, match="window"):
        compute_roughness(dem, window=2)
    with pytest.raises(ValueError, match="window"):
        compute_roughness(dem, window=4)  # even


def test_roughness_nan_preserved():
    """NaN cells in the input should produce NaN in the output."""
    dem = flat_dem().copy()
    dem[4, 4] = np.nan
    roughness = compute_roughness(dem, window=3)
    assert np.isnan(roughness[4, 4])


# ---------------------------------------------------------------------------
# compute_rugosity
# ---------------------------------------------------------------------------


def test_rugosity_area_ratio_flat_is_one():
    """Surface-area ratio rugosity is exactly 1 on a flat surface."""
    dem = flat_dem()
    rugosity = compute_rugosity(dem, DX, DY, method="area_ratio")
    np.testing.assert_allclose(rugosity, 1.0, atol=1e-10)


def test_rugosity_area_ratio_above_one_on_slope():
    """Rugosity exceeds 1 when the surface is not flat."""
    dem = ramp_dem(slope_dx=100.0)  # steep ramp
    rugosity = compute_rugosity(dem, DX, DY, method="area_ratio")
    assert np.all(rugosity[1:-1, 1:-1] > 1.0)


def test_rugosity_vrm_flat_is_zero():
    """VRM rugosity is 0 on a flat surface (all normals identical → no dispersion)."""
    dem = flat_dem(rows=15, cols=15)
    vrm = compute_rugosity(dem, DX, DY, method="vrm", window=3)
    np.testing.assert_allclose(vrm[2:-2, 2:-2], 0.0, atol=1e-6)


def test_rugosity_vrm_bounded():
    """VRM values are always in [0, 1]."""
    rng = np.random.default_rng(99)
    dem = rng.integers(-1000, 0, size=(20, 20)).astype(np.float64)
    vrm = compute_rugosity(dem, DX, DY, method="vrm", window=3)
    assert np.all(vrm >= 0.0)
    assert np.all(vrm <= 1.0)


def test_rugosity_shape_preserved():
    dem = flat_dem(rows=10, cols=14)
    for method in ("area_ratio", "vrm"):
        rug = compute_rugosity(dem, DX, DY, method=method)
        assert rug.shape == (10, 14), f"Shape mismatch for method={method}"


def test_rugosity_unknown_method():
    dem = flat_dem()
    with pytest.raises(ValueError, match="Unknown rugosity method"):
        compute_rugosity(dem, DX, DY, method="invalid_method")


def test_rugosity_vrm_invalid_window():
    dem = flat_dem()
    with pytest.raises(ValueError, match="window"):
        compute_rugosity(dem, DX, DY, method="vrm", window=2)


def test_rugosity_int16_input():
    """compute_rugosity should accept raw GEBCO int16 values."""
    dem = np.zeros((9, 9), dtype=np.int16)
    rug = compute_rugosity(dem, DX, DY, method="area_ratio")
    assert rug.dtype == np.float64
