"""Terrain-context hook: bbox fallback + DEM-backed classification.

The bbox-fallback tests and the pure elevation mapping run with no optional
deps. The real GEBCO-sampling test is guarded by ``importorskip("xarray")``.
"""

from __future__ import annotations

import math

import pytest

from gebco.terrain import classify_elevation, classify_point
from pipeline import terrain_hook
from pipeline.terrain_hook import get_terrain_context


@pytest.fixture(autouse=True)
def _no_gebco(monkeypatch):
    """Default every test to the no-DEM fallback path (clean env + cache)."""
    monkeypatch.delenv("SPIDERWEB_GEBCO_NC", raising=False)
    terrain_hook._gebco_ds_cache.clear()
    yield
    terrain_hook._gebco_ds_cache.clear()


# ── Fallback (no DEM configured) — must match the original bbox behaviour ──────

def test_fallback_urban() -> None:
    assert get_terrain_context(18.42, -66.05) == "urban"  # San Juan metro box


def test_fallback_offshore_out_of_lat_band() -> None:
    assert get_terrain_context(19.5, -66.0) == "offshore"


def test_fallback_coastal_lon_fringe() -> None:
    assert get_terrain_context(18.10, -67.40) == "coastal"
    assert get_terrain_context(18.10, -65.40) == "coastal"


def test_fallback_inland() -> None:
    assert get_terrain_context(18.20, -66.50) == "inland"


def test_unknown_on_unparseable() -> None:
    assert get_terrain_context("nope", None) == "unknown"


# ── Pure elevation mapping ────────────────────────────────────────────────────

def test_classify_elevation_bands() -> None:
    assert classify_elevation(-50.0) == "offshore"
    assert classify_elevation(-10.0) == "offshore"  # boundary is offshore
    assert classify_elevation(0.0) == "coastal"
    assert classify_elevation(9.9) == "coastal"
    assert classify_elevation(10.0) == "inland"
    assert classify_elevation(250.0) == "inland"


def test_classify_elevation_unknown() -> None:
    assert classify_elevation(None) == "unknown"
    assert classify_elevation(float("nan")) == "unknown"
    assert classify_elevation("nope") == "unknown"


def test_classify_point_with_explicit_elevation() -> None:
    assert classify_point(18.2, -66.5, elevation_m=-30.0) == "offshore"
    assert classify_point(18.2, -66.5, elevation_m=3.0) == "coastal"
    assert classify_point(18.2, -66.5, elevation_m=120.0) == "inland"
    assert classify_point(18.2, -66.5, elevation_m=None) == "unknown"  # no source


# ── DEM-backed terrain_hook path (fake dataset — no xarray needed) ────────────

class _FakeVar:
    def __init__(self, value: float) -> None:
        self._value = value

    def sel(self, **_kwargs) -> "_FakeVar":
        return self

    @property
    def values(self) -> float:
        return self._value


class _FakeDataset:
    """Minimal stand-in for a GEBCO xarray Dataset returning a fixed elevation."""

    def __init__(self, elevation_m: float) -> None:
        self._var = _FakeVar(elevation_m)

    def __getitem__(self, key: str) -> _FakeVar:
        assert key == "elevation"
        return self._var


def _use_fake_dem(monkeypatch, elevation_m: float) -> None:
    monkeypatch.setattr(terrain_hook, "_get_gebco_dataset", lambda: _FakeDataset(elevation_m))


def test_dem_overrides_bbox_offshore(monkeypatch) -> None:
    # A point the bbox heuristic calls 'inland', but the DEM says submerged.
    _use_fake_dem(monkeypatch, -40.0)
    assert get_terrain_context(18.20, -66.50) == "offshore"


def test_dem_overrides_bbox_coastal(monkeypatch) -> None:
    _use_fake_dem(monkeypatch, 2.0)
    assert get_terrain_context(18.20, -66.50) == "coastal"


def test_dem_inland(monkeypatch) -> None:
    _use_fake_dem(monkeypatch, 300.0)
    assert get_terrain_context(18.20, -66.50) == "inland"


def test_urban_wins_over_dem(monkeypatch) -> None:
    # Urban overlay is applied before the DEM, so a metro point stays 'urban'
    # even if the DEM would call it coastal.
    _use_fake_dem(monkeypatch, 1.0)
    assert get_terrain_context(18.42, -66.05) == "urban"


def test_dem_unknown_falls_back_to_bbox(monkeypatch) -> None:
    # If the DEM sample is unusable (NaN), fall through to the bbox heuristic.
    _use_fake_dem(monkeypatch, float("nan"))
    assert get_terrain_context(18.20, -66.50) == "inland"


# ── Real GEBCO sampling via xarray (CI; skipped without the DEM stack) ─────────

def test_classify_point_samples_real_dataset() -> None:
    xr = pytest.importorskip("xarray")
    np = pytest.importorskip("numpy")

    lats = np.array([18.0, 18.25, 18.5])
    lons = np.array([-67.0, -66.5, -66.0])
    # elevation[j, i] at (lat[j], lon[i]); pick a clearly inland cell.
    elev = np.array(
        [[-200.0, -5.0, 50.0],
         [-5.0, 25.0, 400.0],
         [3.0, 120.0, 800.0]],
        dtype="float64",
    )
    ds = xr.Dataset(
        {"elevation": (("lat", "lon"), elev)},
        coords={"lat": lats, "lon": lons},
    )
    assert classify_point(18.25, -66.5, dataset=ds) == "inland"   # 25 m
    assert classify_point(18.0, -67.0, dataset=ds) == "offshore"  # -200 m
    assert classify_point(18.5, -67.0, dataset=ds) == "coastal"   # 3 m
    assert math.isfinite(25.0)  # sanity
