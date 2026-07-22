"""CRS-awareness of the PR DEM terrain-screening pilot (NOAA_NCEI_DEM_GAP_005).

The registered CUDEM tiles are geographic (EPSG:4269). The pilot's downsample /
slope / area math assumes a projected, metre-based CRS, so geographic tiles must
be reprojected first. These tests synthesize small CRS-stamped GeoTIFFs and assert
the pilot reprojects geographic input to NAD83 UTM and then produces metre-scale
results (and that the old, un-reprojected path is the degenerate one).

Skipped when the optional `dem` extra (rasterio) is not installed.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("rasterio")

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.crs import CRS  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
PILOT_PATH = REPO_ROOT / "tools" / "pr_dem_one_tile_pilot.py"


def _load_pilot():
    spec = importlib.util.spec_from_file_location("pr_dem_one_tile_pilot", PILOT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilot = _load_pilot()


def _mesa_dem(n: int = 240, r_flat: int = 8, drop_per_px: float = 5.0) -> np.ndarray:
    """A flat-topped mesa: flat plateau (slope 0) with a steep skirt around it."""
    cy = cx = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    elev = np.where(dist <= r_flat, 100.0, np.maximum(0.0, 100.0 - drop_per_px * (dist - r_flat)))
    return elev.astype("float32")


def _write_tif(path: Path, data: np.ndarray, crs: CRS, transform) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        crs=crs,
        transform=transform,
        nodata=None,
    ) as dst:
        dst.write(data, 1)
    return path


def _geographic_tile(tmp_path: Path) -> Path:
    # ~0.024 deg square near western PR at 1e-4 deg/px -> centroid ~-66.59 -> UTM 19N.
    data = _mesa_dem()
    transform = from_origin(-66.6, 18.42, 1e-4, 1e-4)
    return _write_tif(tmp_path / "cudem_geographic_4269.tif", data, CRS.from_epsg(4269), transform)


def _test_args(**overrides) -> argparse.Namespace:
    base = dict(
        internal_slope_max=3.0,
        surrounding_slope_min=15.0,
        min_area_m2=100.0,
        max_area_m2=100000.0,  # generous: we assert metric correctness, not prod thresholds
        ring_pixels=5,
        tpi_window_pixels=21,
        max_candidates=500,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_pick_utm_epsg_selects_pr_zones() -> None:
    assert pilot.pick_utm_epsg(-66.5) == 26919  # zone 19N (mainland PR)
    assert pilot.pick_utm_epsg(-65.5) == 26920  # zone 20N (Vieques / Culebra / east)


def test_geographic_tile_is_reprojected_to_metric(tmp_path: Path) -> None:
    tile = _geographic_tile(tmp_path)
    dem, transform, crs, meta = pilot.read_dem(tile, target_resolution_m=5.0)

    # Reprojected to a NAD83 UTM CRS, and the working transform is now metre-based.
    assert meta["reprojected_to"] is not None
    assert meta["reprojected_to"].startswith("EPSG:269")
    assert crs.startswith("EPSG:269")
    # Metre pixel size is O(target_resolution) — not ~2.78e-5 degrees.
    assert 1.0 < abs(transform.a) < 60.0
    # The tile is NOT collapsed to 1x1 (the pre-fix failure).
    assert meta["output_width"] > 10 and meta["output_height"] > 10


def test_no_reproject_flag_reproduces_the_degenerate_collapse(tmp_path: Path) -> None:
    tile = _geographic_tile(tmp_path)
    _, transform, crs, meta = pilot.read_dem(tile, target_resolution_m=5.0, reproject=False)
    # Native degree pixels (~2.78e-5) against a 5 m target collapse the tile.
    assert crs == "EPSG:4269"
    assert meta["reprojected_to"] is None
    assert meta["output_width"] == 1 and meta["output_height"] == 1


def test_reprojected_tile_yields_metre_scale_candidates(tmp_path: Path) -> None:
    tile = _geographic_tile(tmp_path)
    dem, transform, crs, _ = pilot.read_dem(tile, target_resolution_m=5.0)
    rows = pilot.extract_rows(dem, transform, crs, tile, _test_args())

    assert rows, "expected the flat mesa top to be detected after reprojection"
    top = rows[0]
    # Areas are metre-scale (hundreds+ of m^2), not degree^2 dust.
    assert top["area_m2"] >= 100.0
    assert top["mean_slope_deg"] <= 3.0  # the flat plateau
    assert top["ring_mean_slope_deg"] >= 15.0  # steep skirt around it
    assert top["lon"] is not None and -67.5 < top["lon"] < -65.0


def test_assume_source_crs_recovers_crsless_tile(tmp_path: Path) -> None:
    # A GeoTIFF with NO embedded CRS + degree spacing: --assume-source-crs must
    # let the WarpedVRT reproject it (src_crs is threaded through, not just a local).
    data = _mesa_dem()
    transform = from_origin(-66.6, 18.42, 1e-4, 1e-4)
    tile = tmp_path / "dem_no_crs.tif"
    with rasterio.open(
        tile, "w", driver="GTiff", height=data.shape[0], width=data.shape[1],
        count=1, dtype=data.dtype, transform=transform,  # no crs=
    ) as dst:
        dst.write(data, 1)

    with rasterio.open(tile) as chk:
        assert chk.crs is None  # precondition: genuinely CRS-less

    dem, out_transform, crs, meta = pilot.read_dem(
        tile, target_resolution_m=5.0, assume_source_crs="EPSG:4269"
    )
    assert meta["source_crs"] == "EPSG:4269"
    assert meta["reprojected_to"] is not None and meta["reprojected_to"].startswith("EPSG:269")
    assert crs.startswith("EPSG:269")
    assert 1.0 < abs(out_transform.a) < 60.0
    assert meta["output_width"] > 10 and meta["output_height"] > 10


def test_projected_tile_passes_through_unchanged(tmp_path: Path) -> None:
    # A 5 m NAD83 UTM 19N tile is already metric: no reprojection, math works.
    data = _mesa_dem()
    transform = from_origin(200000.0, 2035000.0, 5.0, 5.0)
    tile = _write_tif(tmp_path / "dem_utm_26919.tif", data, CRS.from_epsg(26919), transform)

    dem, out_transform, crs, meta = pilot.read_dem(tile, target_resolution_m=5.0)
    assert meta["reprojected_to"] is None
    assert crs == "EPSG:26919"
    assert abs(out_transform.a) == pytest.approx(5.0, abs=0.5)
    rows = pilot.extract_rows(dem, out_transform, crs, tile, _test_args())
    assert rows and rows[0]["area_m2"] >= 100.0
