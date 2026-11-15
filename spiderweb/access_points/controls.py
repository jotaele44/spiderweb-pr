"""Synthetic control surfaces with known answers.

These surfaces verify the *software*: a planted basin must be found, a plane
must yield nothing, a survey seam must be flagged.  They say nothing about how
the methods perform on real ground or real seabed.  Results obtained on them
are labelled ``SYNTHETIC_CONTROL`` and can never be reported as scientific
precision or recall.

Every generator is deterministic for a given seed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CONTROLS_VERSION = "access-point-synthetic-controls/1.0"


@dataclass(frozen=True, slots=True)
class PlantedFeature:
    """Where a synthetic feature was put and how big it is, in cell units."""

    name: str
    shape: str
    row: float
    col: float
    radius_cells: float
    depth_m: float


def tilted_plane(rows: int, cols: int, *, base_m: float = 100.0, slope_x: float = 0.02,
                 slope_y: float = 0.01) -> np.ndarray:
    """A plane with no closed basins.  The basic negative control."""

    yy, xx = np.mgrid[0:rows, 0:cols].astype(np.float64)
    return base_m + slope_x * xx + slope_y * yy


def add_gaussian_basin(surface: np.ndarray, row: float, col: float, *, depth_m: float,
                       sigma_cells: float) -> np.ndarray:
    """A smooth bowl, like a solution doline or a sediment-draped depression."""

    yy, xx = np.mgrid[0 : surface.shape[0], 0 : surface.shape[1]].astype(np.float64)
    bowl = np.exp(-(((xx - col) ** 2 + (yy - row) ** 2) / (2.0 * sigma_cells**2)))
    return surface - depth_m * bowl


def add_steep_pit(surface: np.ndarray, row: float, col: float, *, depth_m: float,
                  radius_cells: float, wall_cells: float = 1.5) -> np.ndarray:
    """A near-vertical-walled circular pit with a flat floor."""

    yy, xx = np.mgrid[0 : surface.shape[0], 0 : surface.shape[1]].astype(np.float64)
    dist = np.hypot(xx - col, yy - row)
    profile = np.clip((radius_cells - dist) / wall_cells, 0.0, 1.0)
    return surface - depth_m * profile


def add_rectangular_cut(surface: np.ndarray, row0: int, col0: int, row1: int, col1: int, *,
                        floor_m: float) -> np.ndarray:
    """A flat-floored rectangular cut, like a quarry bench or a dredged box."""

    out = surface.copy()
    out[row0:row1, col0:col1] = np.minimum(out[row0:row1, col0:col1], floor_m)
    return out


def add_noise(surface: np.ndarray, *, sigma_m: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return surface + rng.normal(0.0, sigma_m, surface.shape)


def add_column_seam(surface: np.ndarray, col: int, *, step_m: float) -> np.ndarray:
    """A vertical bias between two adjoining surveys along a north-south line."""

    out = surface.copy()
    out[:, col:] += step_m
    return out


def add_nodata_block(surface: np.ndarray, row0: int, col0: int, row1: int, col1: int) -> np.ndarray:
    out = surface.copy()
    out[row0:row1, col0:col1] = np.nan
    return out


def interpolation_mask(shape: tuple[int, int], row0: int, col0: int, row1: int, col1: int) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[row0:row1, col0:col1] = True
    return mask


def karst_plateau_scene(rows: int = 320, cols: int = 320, *, seed: int = 11,
                        noise_m: float = 0.03) -> tuple[np.ndarray, tuple[PlantedFeature, ...]]:
    """A land scene: three natural-looking basins and one rectangular cut."""

    surface = tilted_plane(rows, cols, base_m=120.0, slope_x=0.015, slope_y=0.008)
    planted = (
        PlantedFeature("basin_a", "gaussian", 80.0, 90.0, 9.0, 5.0),
        PlantedFeature("basin_b", "gaussian", 210.0, 70.0, 12.0, 8.0),
        PlantedFeature("pit_c", "steep", 150.0, 230.0, 8.0, 12.0),
        PlantedFeature("cut_d", "rectangle", 255.0, 215.0, 15.0, 6.0),
    )
    surface = add_gaussian_basin(surface, 80.0, 90.0, depth_m=5.0, sigma_cells=9.0)
    surface = add_gaussian_basin(surface, 210.0, 70.0, depth_m=8.0, sigma_cells=12.0)
    surface = add_steep_pit(surface, 150.0, 230.0, depth_m=12.0, radius_cells=8.0)
    floor = float(surface[240:270, 195:235].min()) - 6.0
    surface = add_rectangular_cut(surface, 240, 195, 270, 235, floor_m=floor)
    if noise_m > 0:
        surface = add_noise(surface, sigma_m=noise_m, seed=seed)
    return surface, planted


def shelf_scene(rows: int = 320, cols: int = 320, *, seed: int = 23,
                noise_m: float = 0.05) -> tuple[np.ndarray, tuple[PlantedFeature, ...]]:
    """A seabed scene, elevation positive up: a gently dipping shelf at about
    -30 m with one steep circular pit and one broad shallow depression."""

    surface = tilted_plane(rows, cols, base_m=-25.0, slope_x=-0.02, slope_y=-0.01)
    planted = (
        PlantedFeature("pit_a", "steep", 110.0, 120.0, 10.0, 25.0),
        PlantedFeature("swale_b", "gaussian", 220.0, 210.0, 20.0, 3.0),
    )
    surface = add_steep_pit(surface, 110.0, 120.0, depth_m=25.0, radius_cells=10.0, wall_cells=2.0)
    surface = add_gaussian_basin(surface, 220.0, 210.0, depth_m=3.0, sigma_cells=20.0)
    if noise_m > 0:
        surface = add_noise(surface, sigma_m=noise_m, seed=seed)
    return surface, planted
