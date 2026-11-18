"""Shared surface processing for terrain and bathymetry.

One processing core serves LiDAR terrain models, topobathymetric models and
gridded sonar bathymetry.  It does not pretend they are the same measurement:

* a :class:`SurfaceGrid` records what kind of surface it is, which source it
  came from, which cells were measured and which were interpolated;
* only *elevation* surfaces can be analysed for depressions.  An intensity
  raster (side-scan mosaic, backscatter) is not a depth surface and is refused;
* a grid without a horizontal CRS, or an elevation grid without a known
  vertical datum, cannot be constructed;
* no-data stays no-data.  Depression filling drains into no-data, so a closed
  basin is never invented out of cells nobody measured;
* results are deterministic: the same input bytes give the same output bytes,
  tiled or untiled.

Slope and curvature are the existing :mod:`gebco.terrain` implementations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Iterator, Sequence

import numpy as np
from scipy import ndimage
from skimage import measure
from skimage.morphology import reconstruction

from gebco.marine_evidence import VerticalCompatibilityError, VerticalReference
from gebco.terrain import compute_curvatures, compute_slope

from .vertical import BoundVertical, CertifiedTransform, DatumKind, bind

PROCESSING_VERSION = "access-point-surface-processing/1.0"

# Fill depths at or below this are numerical residue, not relief.
NUMERICAL_DEPTH_FLOOR_M = 1e-6


class MissingCRSError(ValueError):
    """A grid was offered without a horizontal coordinate reference system."""


class SignConventionError(ValueError):
    """Values contradict the declared elevation/depth sign convention."""


class NotAnElevationSurfaceError(ValueError):
    """A height operation was requested on a raster that is not a height surface."""


class GridMismatchError(ValueError):
    """Two grids do not share the same cells."""


class SurfaceKind(StrEnum):
    TERRAIN_BARE_EARTH = "TERRAIN_BARE_EARTH"
    TERRAIN_FIRST_RETURN = "TERRAIN_FIRST_RETURN"
    BATHYMETRY = "BATHYMETRY"
    TOPOBATHYMETRY = "TOPOBATHYMETRY"
    BACKSCATTER_INTENSITY = "BACKSCATTER_INTENSITY"
    SIDESCAN_INTENSITY = "SIDESCAN_INTENSITY"


ELEVATION_KINDS = frozenset(
    {
        SurfaceKind.TERRAIN_BARE_EARTH,
        SurfaceKind.TERRAIN_FIRST_RETURN,
        SurfaceKind.BATHYMETRY,
        SurfaceKind.TOPOBATHYMETRY,
    }
)


@dataclass(frozen=True)
class SurfaceGrid:
    """A north-up raster.  Elevation values are metres, positive up, NaN = no data.

    ``origin`` is the outer corner of the north-west cell in ``crs`` units.
    ``cell_size_m`` is the ground size of a cell in metres (east-west,
    north-south); for a geographic CRS it must be supplied explicitly.
    """

    values: np.ndarray
    cell_size_m: tuple[float, float]
    origin: tuple[float, float]
    cell_size_crs: tuple[float, float]
    crs: str
    kind: SurfaceKind
    vertical: BoundVertical | None
    source_id: str | None = None
    interpolated: np.ndarray | None = None
    uncertainty_m: float | np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.values.shape  # type: ignore[return-value]

    @property
    def is_elevation(self) -> bool:
        return self.kind in ELEVATION_KINDS

    @property
    def valid(self) -> np.ndarray:
        return np.isfinite(self.values)

    @property
    def cell_area_m2(self) -> float:
        return self.cell_size_m[0] * self.cell_size_m[1]

    def xy(self, row: float, col: float) -> tuple[float, float]:
        """CRS coordinates of a (fractional) cell position; cell centres are +0.5."""

        return (
            float(self.origin[0] + col * self.cell_size_crs[0]),
            float(self.origin[1] - row * self.cell_size_crs[1]),
        )

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        return self.xy(row + 0.5, col + 0.5)

    def uncertainty_array(self) -> np.ndarray | None:
        if self.uncertainty_m is None:
            return None
        if np.isscalar(self.uncertainty_m):
            return np.full(self.shape, float(self.uncertainty_m))  # type: ignore[arg-type]
        return np.asarray(self.uncertainty_m, dtype=np.float64)


def make_grid(
    values: np.ndarray,
    *,
    cell_size_m: tuple[float, float],
    origin: tuple[float, float],
    crs: str | None,
    kind: SurfaceKind,
    vertical_reference: VerticalReference | BoundVertical | None = None,
    cell_size_crs: tuple[float, float] | None = None,
    nodata: float | None = None,
    interpolated: np.ndarray | None = None,
    uncertainty_m: float | np.ndarray | None = None,
    source_id: str | None = None,
    expect: str | None = None,
) -> SurfaceGrid:
    """Build a validated grid.  Fails closed on missing CRS, datum or bad sign.

    ``expect`` may be ``"submerged"`` or ``"emergent"``.  When given, a surface
    whose valid cells lie overwhelmingly on the wrong side of its datum is
    rejected as a sign-convention error rather than silently analysed upside
    down.
    """

    if crs is None or not str(crs).strip():
        raise MissingCRSError("a grid must state its horizontal CRS")
    array = np.array(values, dtype=np.float64, copy=True)
    if array.ndim != 2 or array.size == 0:
        raise ValueError("values must be a non-empty 2-D array")
    dx, dy = (float(cell_size_m[0]), float(cell_size_m[1]))
    if not (math.isfinite(dx) and math.isfinite(dy) and dx > 0 and dy > 0):
        raise ValueError("cell_size_m must be two positive finite numbers")
    crs_cell = (
        (dx, dy)
        if cell_size_crs is None
        else (float(cell_size_crs[0]), float(cell_size_crs[1]))
    )
    if not (crs_cell[0] > 0 and crs_cell[1] > 0):
        raise ValueError("cell_size_crs must be positive")
    if nodata is not None:
        if math.isnan(nodata):
            pass
        else:
            array[array == nodata] = np.nan
    array[~np.isfinite(array)] = np.nan

    bound: BoundVertical | None = None
    if kind in ELEVATION_KINDS:
        bound = (
            vertical_reference
            if isinstance(vertical_reference, BoundVertical)
            else bind(vertical_reference)
        )
        if bound.positive == "down":
            array = -array
            bound = BoundVertical(bound.datum, "up", bound.horizontal_crs)
    elif vertical_reference is not None:
        raise NotAnElevationSurfaceError(
            f"{kind.value} is not a height surface and carries no vertical reference"
        )

    mask = None
    if interpolated is not None:
        mask = np.array(interpolated, dtype=bool, copy=True)
        if mask.shape != array.shape:
            raise GridMismatchError("interpolated mask shape differs from values")
    unc: float | np.ndarray | None = None
    if uncertainty_m is not None:
        if np.isscalar(uncertainty_m):
            unc = float(uncertainty_m)  # type: ignore[arg-type]
            if not math.isfinite(unc) or unc < 0:
                raise ValueError("uncertainty_m must be finite and non-negative")
        else:
            unc = np.array(uncertainty_m, dtype=np.float64, copy=True)
            if unc.shape != array.shape:
                raise GridMismatchError("uncertainty shape differs from values")
            if np.any(unc[np.isfinite(unc)] < 0):
                raise ValueError("uncertainty_m must be non-negative")

    if expect is not None:
        if expect not in {"submerged", "emergent"}:
            raise ValueError("expect must be 'submerged' or 'emergent'")
        if kind not in ELEVATION_KINDS:
            raise NotAnElevationSurfaceError(
                "sign expectation applies to height surfaces only"
            )
        finite = array[np.isfinite(array)]
        if finite.size:
            above = float(np.mean(finite > 0))
            if expect == "submerged" and above > 0.95:
                raise SignConventionError(
                    "surface declared submerged, yet over 95% of cells are above the datum "
                    "after sign normalisation; the declared depth sign is wrong"
                )
            if expect == "emergent" and above < 0.05:
                raise SignConventionError(
                    "surface declared emergent, yet over 95% of cells are below the datum "
                    "after sign normalisation; the declared elevation sign is wrong"
                )

    array.setflags(write=False)
    if mask is not None:
        mask.setflags(write=False)
    if isinstance(unc, np.ndarray):
        unc.setflags(write=False)
    return SurfaceGrid(
        values=array,
        cell_size_m=(dx, dy),
        origin=(float(origin[0]), float(origin[1])),
        cell_size_crs=crs_cell,
        crs=str(crs).strip(),
        kind=kind,
        vertical=bound,
        source_id=source_id,
        interpolated=mask,
        uncertainty_m=unc,
    )


def _require_elevation(grid: SurfaceGrid, operation: str) -> None:
    if not grid.is_elevation:
        raise NotAnElevationSurfaceError(
            f"{operation} needs a measured height surface; {grid.kind.value} is an intensity raster"
        )


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    total_cells: int
    valid_cells: int
    nodata_cells: int
    interpolated_cells: int | None
    measured_cells: int | None

    @property
    def valid_fraction(self) -> float:
        return self.valid_cells / self.total_cells

    @property
    def measured_fraction(self) -> float | None:
        if self.measured_cells is None:
            return None
        return self.measured_cells / self.total_cells

    def closes(self) -> bool:
        ok = self.valid_cells + self.nodata_cells == self.total_cells
        if self.interpolated_cells is not None and self.measured_cells is not None:
            ok = (
                ok and self.interpolated_cells + self.measured_cells == self.valid_cells
            )
        return ok


def coverage(grid: SurfaceGrid) -> CoverageSummary:
    """Cell accounting.  When no interpolation mask exists, measured is unknown."""

    valid = grid.valid
    total = int(valid.size)
    n_valid = int(valid.sum())
    if grid.interpolated is None:
        return CoverageSummary(total, n_valid, total - n_valid, None, None)
    interp = int((grid.interpolated & valid).sum())
    return CoverageSummary(total, n_valid, total - n_valid, interp, n_valid - interp)


def slope_degrees(grid: SurfaceGrid) -> np.ndarray:
    _require_elevation(grid, "slope")
    slope, _, _ = compute_slope(grid.values, grid.cell_size_m[0], grid.cell_size_m[1])
    return slope


def curvatures(grid: SurfaceGrid) -> dict[str, np.ndarray]:
    _require_elevation(grid, "curvature")
    result = compute_curvatures(grid.values, grid.cell_size_m[0], grid.cell_size_m[1])
    if isinstance(result, dict):
        return result
    names = ("profile", "plan", "general")
    return {name: arr for name, arr in zip(names, result)}


def _disk(radius: int, inner: int = 0) -> np.ndarray:
    yy, xx = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    dist2 = yy * yy + xx * xx
    kernel = (dist2 <= radius * radius) & (dist2 >= inner * inner)
    if inner == 0:
        kernel[radius, radius] = False
    return kernel.astype(np.float64)


def position_index(
    grid: SurfaceGrid, outer_radius_cells: int, inner_radius_cells: int = 0
) -> np.ndarray:
    """Cell height minus the mean height of its neighbourhood.

    The topographic position index on land and the bathymetric position index
    at sea are the same statistic.  Negative values are local lows.  Cells
    whose neighbourhood holds no valid data are NaN.
    """

    _require_elevation(grid, "position index")
    if (
        outer_radius_cells < 1
        or inner_radius_cells < 0
        or inner_radius_cells >= outer_radius_cells
    ):
        raise ValueError("radii must satisfy 0 <= inner < outer and outer >= 1")
    kernel = _disk(int(outer_radius_cells), int(inner_radius_cells))
    valid = grid.valid
    filled = np.where(valid, grid.values, 0.0)
    total = ndimage.convolve(filled, kernel, mode="constant", cval=0.0)
    count = ndimage.convolve(
        valid.astype(np.float64), kernel, mode="constant", cval=0.0
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(count > 0, total / count, np.nan)
    return np.where(valid, grid.values - mean, np.nan)


def local_relief(grid: SurfaceGrid, radius_cells: int) -> np.ndarray:
    """Range of valid heights within a square window."""

    _require_elevation(grid, "local relief")
    if radius_cells < 1:
        raise ValueError("radius_cells must be at least 1")
    size = 2 * int(radius_cells) + 1
    valid = grid.valid
    high = ndimage.maximum_filter(
        np.where(valid, grid.values, -np.inf), size=size, mode="constant", cval=-np.inf
    )
    low = ndimage.minimum_filter(
        np.where(valid, grid.values, np.inf), size=size, mode="constant", cval=np.inf
    )
    relief = high - low
    return np.where(valid & np.isfinite(relief), relief, np.nan)


def hillshade(
    grid: SurfaceGrid, azimuth_deg: float = 315.0, altitude_deg: float = 45.0
) -> np.ndarray:
    """Shaded relief in [0, 1] for display.  A rendering, never evidence."""

    _require_elevation(grid, "hillshade")
    _, dz_dx, dz_dy = compute_slope(
        grid.values, grid.cell_size_m[0], grid.cell_size_m[1]
    )
    slope = np.arctan(np.hypot(dz_dx, dz_dy))
    aspect = np.arctan2(dz_dy, -dz_dx)
    azimuth = math.radians(360.0 - azimuth_deg + 90.0)
    altitude = math.radians(altitude_deg)
    shade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(
        slope
    ) * np.cos(azimuth - aspect)
    return np.where(np.isfinite(shade), np.clip(shade, 0.0, 1.0), np.nan)


def fill_depressions(grid: SurfaceGrid) -> np.ndarray:
    """Raise every closed basin to its spill level.

    No-data cells and the grid edge are outlets.  A basin that could drain
    into unmeasured ground is therefore not closed, and is not reported.
    """

    _require_elevation(grid, "depression filling")
    values = grid.values
    valid = grid.valid
    if not valid.any():
        return np.full(values.shape, np.nan)
    floor = float(np.nanmin(values)) - 1.0
    surface = np.where(valid, values, floor)
    padded = np.pad(surface, 1, mode="constant", constant_values=floor)
    seed = np.full(padded.shape, float(np.nanmax(values)), dtype=np.float64)
    outlet = padded == floor
    seed[outlet] = floor
    seed = np.maximum(seed, padded)
    seed[outlet] = floor
    filled = reconstruction(seed, padded, method="erosion")[1:-1, 1:-1]
    return np.where(valid, filled, np.nan)


def depression_depth(grid: SurfaceGrid) -> np.ndarray:
    filled = fill_depressions(grid)
    depth = filled - grid.values
    return np.where(grid.valid, np.maximum(depth, 0.0), np.nan)


@dataclass(frozen=True, slots=True)
class DepressionRegion:
    """One closed basin and the shape measurements taken from it."""

    label: int
    cell_count: int
    area_m2: float
    max_depth_m: float
    mean_depth_m: float
    volume_m3: float
    spill_elevation_m: float
    floor_elevation_m: float
    centroid_xy: tuple[float, float]
    deepest_xy: tuple[float, float]
    bbox_xy: tuple[float, float, float, float]
    equivalent_diameter_m: float
    depth_to_diameter: float
    circularity: float
    elongation: float
    solidity: float
    rectangularity: float
    mean_wall_slope_deg: float | None
    flat_floor_fraction: float | None
    adjoins_nodata: bool
    adjoins_edge: bool
    interpolated_fraction: float | None
    depth_uncertainty_m: float | None
    significance: float | None
    slices: tuple[slice, slice]
    # 0 for a basin closed against the surrounding ground; 1 and up for a basin
    # nested inside another (see ``delineate_depressions(nested=True)``).
    hierarchy_level: int = 0
    parent_deepest_xy: tuple[float, float] | None = None
    # A nested basin's depth is measured from the level at which it is seen to
    # be separate, so it is a lower bound good to this step.  ``None`` for an
    # outer basin, whose spill level is exact.
    depth_resolution_m: float | None = None


@dataclass(frozen=True)
class _MeasureContext:
    grid: SurfaceGrid
    slope: np.ndarray
    uncertainty: np.ndarray | None
    valid: np.ndarray


_STRUCTURE8 = np.ones((3, 3), dtype=bool)
_MAX_NESTED_LEVELS = 400


def _measure_region(
    context: _MeasureContext,
    member: np.ndarray,
    window: tuple[slice, slice],
    depth_here: np.ndarray,
    *,
    spill_elevation_m: float,
    label: int,
    hierarchy_level: int = 0,
    parent_deepest_xy: tuple[float, float] | None = None,
    depth_resolution_m: float | None = None,
) -> DepressionRegion:
    """Measure one basin.  ``member`` and ``depth_here`` cover ``window``.

    Outer and nested basins are measured by this one function, so a depth, an
    area or a shape figure means the same thing for both.
    """

    grid = context.grid
    rows, cols = grid.shape
    dx, dy = grid.cell_size_m
    r0, r1 = window[0].start, window[0].stop
    c0, c1 = window[1].start, window[1].stop
    prop = measure.regionprops(member.astype(np.uint8))[0]
    d = depth_here[member]
    max_depth = float(d.max())
    area = float(prop.area) * grid.cell_area_m2
    h0, h1 = max(r0 - 1, 0), min(r1 + 1, rows)
    w0, w1 = max(c0 - 1, 0), min(c1 + 1, cols)
    placed = np.zeros((h1 - h0, w1 - w0), dtype=bool)
    placed[r0 - h0 : r1 - h0, c0 - w0 : c1 - w0] = member
    ring = ndimage.binary_dilation(placed, structure=_STRUCTURE8)
    adjoins_nodata = bool((ring & ~context.valid[h0:h1, w0:w1]).any())
    adjoins_edge = r0 == 0 or c0 == 0 or r1 == rows or c1 == cols
    # Crofton's estimator: unbiased for curved outlines, where counting
    # boundary cells overstates the perimeter and understates circularity.
    perimeter_cells = (
        float(measure.perimeter_crofton(member, directions=4)) if prop.area > 1 else 4.0
    )
    perimeter_m = perimeter_cells * math.sqrt(dx * dy)
    circularity = (
        min(1.0, 4.0 * math.pi * area / (perimeter_m * perimeter_m))
        if perimeter_m > 0
        else 0.0
    )
    major = float(prop.axis_major_length) or 1.0
    minor = float(prop.axis_minor_length) or 1.0
    diameter = 2.0 * math.sqrt(area / math.pi)
    s = context.slope[window][member]
    s = s[np.isfinite(s)]
    local = np.unravel_index(
        int(np.argmax(np.where(member, depth_here, -1.0))), member.shape
    )
    deepest = (r0 + int(local[0]), c0 + int(local[1]))
    interp_fraction = None
    if grid.interpolated is not None:
        interp_fraction = float(grid.interpolated[window][member].mean())
    depth_unc = None
    significance = None
    if context.uncertainty is not None:
        u = context.uncertainty[window][member]
        u = u[np.isfinite(u)]
        if u.size:
            # Depth is a difference of two heights (floor and spill rim).
            depth_unc = float(math.sqrt(2.0) * np.max(u))
            significance = max_depth / depth_unc if depth_unc > 0 else None
    cy, cx = prop.centroid
    west, north = grid.xy(r0, c0)
    east, south = grid.xy(r1, c1)
    return DepressionRegion(
        label=label,
        cell_count=int(prop.area),
        area_m2=area,
        max_depth_m=max_depth,
        mean_depth_m=float(d.mean()),
        volume_m3=float(d.sum()) * grid.cell_area_m2,
        spill_elevation_m=float(spill_elevation_m),
        floor_elevation_m=float(grid.values[deepest]),
        centroid_xy=grid.xy(r0 + cy + 0.5, c0 + cx + 0.5),
        deepest_xy=grid.cell_center(*deepest),
        bbox_xy=(west, south, east, north),
        equivalent_diameter_m=diameter,
        depth_to_diameter=max_depth / diameter if diameter > 0 else 0.0,
        circularity=float(circularity),
        elongation=major / minor if minor > 0 else float("inf"),
        solidity=float(prop.solidity),
        rectangularity=float(prop.extent),
        mean_wall_slope_deg=float(s.mean()) if s.size else None,
        flat_floor_fraction=float((s < 2.0).mean()) if s.size else None,
        adjoins_nodata=adjoins_nodata,
        adjoins_edge=bool(adjoins_edge),
        interpolated_fraction=interp_fraction,
        depth_uncertainty_m=depth_unc,
        significance=significance,
        slices=window,
        hierarchy_level=hierarchy_level,
        parent_deepest_xy=parent_deepest_xy,
        depth_resolution_m=depth_resolution_m,
    )


def _nested_within(
    context: _MeasureContext,
    member: np.ndarray,
    window: tuple[slice, slice],
    *,
    spill_level: float,
    parent: DepressionRegion,
    min_depth_m: float,
    min_area_m2: float,
    step_m: float,
    first_label: int,
) -> list[DepressionRegion]:
    """Basins nested inside one basin, found by lowering the water level.

    Filling raises a compound depression -- several hollows sharing one rim --
    to a single spill level, so it is one basin.  Lower the level in steps and
    the water body eventually separates.  Where it separates into **two or
    more** parts that each still meet the depth and area thresholds, each part
    is a nested basin, and the same rule is applied inside it.

    * A part that falls below the thresholds is a bump in the floor, not a
      basin, and does not make a split.
    * One deep pit in a broad shallow bowl does not separate the water body
      and is therefore not reported apart from the bowl.  That is a stated
      limit of this rule, not an oversight.
    * A nested basin's depth is measured from the level at which it is seen
      to be separate.  Its true rim lies less than one step higher, so the
      depth is a lower bound and is never overstated.
    """

    grid = context.grid
    out: list[DepressionRegion] = []
    label = first_label
    # (mask, window, level it is known to be one body at, parent region)
    pending = [(member, window, spill_level, parent)]
    while pending:
        mask, win, top, owner = pending.pop()
        z = grid.values[win]
        floor = float(z[mask].min())
        span = top - floor
        if span < min_depth_m:
            continue
        step = max(step_m, span / _MAX_NESTED_LEVELS)
        level = top - step
        while level - floor >= min_depth_m:
            wet = mask & (z < level)
            parts, count = ndimage.label(wet, structure=_STRUCTURE8)
            if count == 0:
                break
            if count >= 2:
                index = np.arange(1, count + 1)
                floors = np.asarray(ndimage.minimum(z, parts, index), dtype=np.float64)
                cells = np.bincount(parts.ravel(), minlength=count + 1)[1:]
                keep = (level - floors >= min_depth_m) & (
                    cells * grid.cell_area_m2 >= min_area_m2
                )
                if int(keep.sum()) >= 2:
                    boxes = ndimage.find_objects(parts)
                    for part in index[keep]:
                        box = boxes[int(part) - 1]
                        sub = (
                            slice(
                                win[0].start + box[0].start, win[0].start + box[0].stop
                            ),
                            slice(
                                win[1].start + box[1].start, win[1].start + box[1].stop
                            ),
                        )
                        sub_mask = parts[box] == part
                        depth_here = np.where(sub_mask, level - grid.values[sub], 0.0)
                        child = _measure_region(
                            context,
                            sub_mask,
                            sub,
                            depth_here,
                            spill_elevation_m=level,
                            label=label,
                            hierarchy_level=owner.hierarchy_level + 1,
                            parent_deepest_xy=owner.deepest_xy,
                            depth_resolution_m=step,
                        )
                        label += 1
                        out.append(child)
                        pending.append((sub_mask, sub, level, child))
                    break
                if int(keep.sum()) == 1:
                    # The other parts are bumps; carry on inside the one basin.
                    mask = parts == index[keep][0]
                else:
                    break
            level -= step
    return out


def delineate_depressions(
    grid: SurfaceGrid,
    *,
    min_depth_m: float,
    min_area_m2: float,
    max_regions: int | None = None,
    footprint_min_depth_m: float | None = None,
    nested: bool = False,
    nested_level_step_m: float = 0.5,
) -> list[DepressionRegion]:
    """Find closed basins and measure them.  Ordered deepest first, then by label.

    With ``nested=True`` the basins inside a compound depression are reported
    as well (see :func:`_nested_within`).  The outer basins are exactly those
    reported without it.

    A cell belongs to a basin only where its fill depth can be told apart from
    zero.  By default that floor is the uncertainty of a depth (root two times
    the cell's stated vertical uncertainty), or one micrometre where no
    uncertainty is stated; ``footprint_min_depth_m`` overrides it.  Without a
    floor, numerical residue on a level rim spreads a basin's outline far
    beyond the ground that is measurably lower.
    """

    _require_elevation(grid, "depression delineation")
    if min_depth_m <= 0 or min_area_m2 <= 0:
        raise ValueError("min_depth_m and min_area_m2 must be positive")
    if nested and not (math.isfinite(nested_level_step_m) and nested_level_step_m > 0):
        raise ValueError("nested_level_step_m must be positive")
    filled = fill_depressions(grid)
    depth = np.where(grid.valid, np.maximum(filled - grid.values, 0.0), 0.0)
    if footprint_min_depth_m is not None:
        if not (math.isfinite(footprint_min_depth_m) and footprint_min_depth_m >= 0):
            raise ValueError("footprint_min_depth_m must be finite and non-negative")
        floor: float | np.ndarray = float(footprint_min_depth_m)
    else:
        sigma = grid.uncertainty_array()
        floor = (
            NUMERICAL_DEPTH_FLOOR_M
            if sigma is None
            else np.where(
                np.isfinite(sigma),
                np.maximum(math.sqrt(2.0) * sigma, NUMERICAL_DEPTH_FLOOR_M),
                NUMERICAL_DEPTH_FLOOR_M,
            )
        )
    wet = depth > floor
    labels = measure.label(wet, connectivity=2)
    label_count = int(labels.max())
    if label_count == 0:
        return []
    # Sensor noise produces very many tiny basins.  Discard those below the
    # thresholds with vectorised per-label statistics before measuring shape,
    # so the per-region work is spent only on basins that will be reported.
    index = np.arange(1, label_count + 1)
    label_max_depth = np.asarray(
        ndimage.maximum(depth, labels, index), dtype=np.float64
    )
    label_cells = np.bincount(labels.ravel(), minlength=label_count + 1)[1:]
    keep = (label_max_depth >= min_depth_m) & (
        label_cells * grid.cell_area_m2 >= min_area_m2
    )
    if not keep.any():
        return []
    windows = ndimage.find_objects(labels)
    context = _MeasureContext(
        grid=grid,
        slope=slope_degrees(grid),
        uncertainty=grid.uncertainty_array(),
        valid=grid.valid,
    )
    regions: list[DepressionRegion] = []
    next_label = label_count + 1
    for label in index[keep]:
        window = windows[int(label) - 1]
        member = labels[window] == label
        depth_here = depth[window]
        local = np.unravel_index(
            int(np.argmax(np.where(member, depth_here, -1.0))), member.shape
        )
        spill = float(filled[window][local])
        outer = _measure_region(
            context,
            member,
            window,
            depth_here,
            spill_elevation_m=spill,
            label=int(label),
        )
        regions.append(outer)
        if nested:
            for child in _nested_within(
                context,
                member,
                window,
                spill_level=spill,
                parent=outer,
                min_depth_m=min_depth_m,
                min_area_m2=min_area_m2,
                step_m=nested_level_step_m,
                first_label=next_label,
            ):
                regions.append(child)
                next_label = max(next_label, child.label + 1)
    regions.sort(key=lambda r: (-r.max_depth_m, r.label))
    if max_regions is not None:
        regions = regions[: int(max_regions)]
    return regions


@dataclass(frozen=True, slots=True)
class Seam:
    """A straight line along which the surface steps by a near-constant amount."""

    axis: str  # "column" (north-south line) or "row" (east-west line)
    index: int  # the step lies between index and index + 1
    step_m: float
    robust_z: float
    sign_consistency: float
    run_fraction: float


def detect_seams(
    grid: SurfaceGrid,
    *,
    z_threshold: float = 8.0,
    min_sign_consistency: float = 0.9,
    min_run_fraction: float = 0.5,
    min_step_m: float = 0.0,
) -> list[Seam]:
    """Find survey or tile seams: a consistent step along a whole grid line.

    Real relief varies along any straight line.  A join between two surveys
    with a vertical bias steps by nearly the same amount, with the same sign,
    all the way along a row or column.
    """

    _require_elevation(grid, "seam detection")
    seams: list[Seam] = []
    for axis_name, axis in (("column", 1), ("row", 0)):
        step = np.diff(grid.values, axis=axis)
        other = 0 if axis == 1 else 1
        count = np.isfinite(step).sum(axis=other)
        length = step.shape[other]
        with np.errstate(all="ignore"):
            med = np.nanmedian(step, axis=other)
            positive = np.nansum(step > 0, axis=other)
            negative = np.nansum(step < 0, axis=other)
        usable = count >= max(3, int(math.ceil(min_run_fraction * length)))
        if usable.sum() < 5:
            continue
        centre = float(np.median(med[usable]))
        mad = float(np.median(np.abs(med[usable] - centre)))
        scale = 1.4826 * mad
        if scale <= 0:
            scale = float(np.std(med[usable])) or 0.0
        if scale <= 0:
            continue
        for index in np.flatnonzero(usable):
            z = (float(med[index]) - centre) / scale
            if abs(z) < z_threshold or abs(float(med[index])) < min_step_m:
                continue
            consistency = float(max(positive[index], negative[index])) / float(
                count[index]
            )
            if consistency < min_sign_consistency:
                continue
            seams.append(
                Seam(
                    axis=axis_name,
                    index=int(index),
                    step_m=float(med[index]),
                    robust_z=float(z),
                    sign_consistency=consistency,
                    run_fraction=float(count[index]) / float(length),
                )
            )
    seams.sort(key=lambda s: (s.axis, s.index))
    return seams


def seam_mask(
    grid: SurfaceGrid, seams: Sequence[Seam], halo_cells: int = 1
) -> np.ndarray:
    mask = np.zeros(grid.shape, dtype=bool)
    for seam in seams:
        lo = max(seam.index - halo_cells + 1, 0)
        if seam.axis == "column":
            mask[:, lo : seam.index + halo_cells + 1] = True
        else:
            mask[lo : seam.index + halo_cells + 1, :] = True
    return mask


def iter_windows(
    shape: tuple[int, int], tile: int, halo: int = 0
) -> Iterator[tuple[tuple[slice, slice], tuple[slice, slice], tuple[slice, slice]]]:
    """Deterministic row-major tiling.

    Yields ``(read, core_in_read, core)``: the padded window to read, where the
    core sits inside it, and where the core goes in the output.
    """

    if tile < 1 or halo < 0:
        raise ValueError("tile must be >= 1 and halo >= 0")
    rows, cols = shape
    for r0 in range(0, rows, tile):
        for c0 in range(0, cols, tile):
            r1, c1 = min(r0 + tile, rows), min(c0 + tile, cols)
            rr0, cc0 = max(r0 - halo, 0), max(c0 - halo, 0)
            rr1, cc1 = min(r1 + halo, rows), min(c1 + halo, cols)
            yield (
                (slice(rr0, rr1), slice(cc0, cc1)),
                (slice(r0 - rr0, r1 - rr0), slice(c0 - cc0, c1 - cc0)),
                (slice(r0, r1), slice(c0, c1)),
            )


def apply_tiled(
    grid: SurfaceGrid,
    operation: Callable[[SurfaceGrid], np.ndarray],
    *,
    tile: int,
    halo: int,
) -> np.ndarray:
    """Run a neighbourhood operation tile by tile with bounded memory.

    ``halo`` must be at least the operation's neighbourhood radius plus one;
    the result is then identical to the untiled result.
    """

    out = np.full(grid.shape, np.nan, dtype=np.float64)
    unc = (
        grid.uncertainty_array() if isinstance(grid.uncertainty_m, np.ndarray) else None
    )
    for read, inner, core in iter_windows(grid.shape, tile, halo):
        west, north = grid.xy(read[0].start, read[1].start)
        sub = SurfaceGrid(
            values=grid.values[read],
            cell_size_m=grid.cell_size_m,
            origin=(west, north),
            cell_size_crs=grid.cell_size_crs,
            crs=grid.crs,
            kind=grid.kind,
            vertical=grid.vertical,
            source_id=grid.source_id,
            interpolated=None if grid.interpolated is None else grid.interpolated[read],
            uncertainty_m=grid.uncertainty_m if unc is None else unc[read],
        )
        out[core] = operation(sub)[inner]
    return out


def coarsen(grid: SurfaceGrid, factor: int) -> SurfaceGrid:
    """Mean-aggregate to a coarser level for overview display.

    A coarse cell is interpolated if any contributing cell was, and its
    uncertainty is the largest contributing uncertainty (the cells of one
    survey are not independent, so no reduction is claimed).
    """

    if factor < 2:
        raise ValueError("factor must be at least 2")
    rows, cols = grid.shape
    r, c = rows // factor, cols // factor
    if r == 0 or c == 0:
        raise ValueError("grid is smaller than the coarsening factor")
    block = grid.values[: r * factor, : c * factor].reshape(r, factor, c, factor)
    valid = np.isfinite(block)
    count = valid.sum(axis=(1, 3))
    total = np.where(valid, block, 0.0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        values = np.where(count > 0, total / count, np.nan)
    interp = None
    if grid.interpolated is not None:
        interp = (
            grid.interpolated[: r * factor, : c * factor]
            .reshape(r, factor, c, factor)
            .any(axis=(1, 3))
        )
        interp = interp | ((count > 0) & (count < factor * factor))
    unc: float | np.ndarray | None = grid.uncertainty_m
    if isinstance(unc, np.ndarray):
        ublock = unc[: r * factor, : c * factor].reshape(r, factor, c, factor)
        unc = np.nanmax(np.where(valid, ublock, np.nan), axis=(1, 3))
    return SurfaceGrid(
        values=values,
        cell_size_m=(grid.cell_size_m[0] * factor, grid.cell_size_m[1] * factor),
        origin=grid.origin,
        cell_size_crs=(grid.cell_size_crs[0] * factor, grid.cell_size_crs[1] * factor),
        crs=grid.crs,
        kind=grid.kind,
        vertical=grid.vertical,
        source_id=grid.source_id,
        interpolated=interp,
        uncertainty_m=unc,
    )


@dataclass(frozen=True)
class SurfaceDifference:
    """Later surface minus earlier surface, with what can be said about it."""

    delta_m: np.ndarray
    uncertainty_m: np.ndarray | None
    detectable: np.ndarray | None
    transform_authority: str | None
    compared_cells: int
    either_interpolated: np.ndarray | None


def difference(
    earlier: SurfaceGrid,
    later: SurfaceGrid,
    *,
    transforms: Sequence[CertifiedTransform] = (),
    coverage_factor: float = 2.0,
) -> SurfaceDifference:
    """Cell-by-cell change between two surveys of the same ground.

    Refuses grids that do not share cells, grids on different datums without a
    certified transform, and assumed datums.  A change is ``detectable`` only
    where it exceeds ``coverage_factor`` times the combined uncertainty; where
    either uncertainty is unknown, detectability is unknown (``None``), not
    assumed.
    """

    _require_elevation(earlier, "surface difference")
    _require_elevation(later, "surface difference")
    if earlier.shape != later.shape:
        raise GridMismatchError("grids have different shapes")
    if earlier.crs != later.crs:
        raise GridMismatchError("grids are in different horizontal CRSs")
    same_cells = all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9 * max(1.0, abs(a)))
        for a, b in zip(
            earlier.origin + earlier.cell_size_crs, later.origin + later.cell_size_crs
        )
    )
    if not same_cells:
        raise GridMismatchError("grids are not cell-aligned; resample explicitly first")
    assert earlier.vertical is not None and later.vertical is not None
    if DatumKind.ASSUMED in {earlier.vertical.kind, later.vertical.kind}:
        raise VerticalCompatibilityError(
            "a surface on an assumed datum cannot be differenced"
        )

    offset = 0.0
    authority = None
    transform_unc: float | None = 0.0
    if earlier.vertical.datum is not later.vertical.datum:
        matches = [
            t
            for t in transforms
            if t.source is later.vertical.datum and t.target is earlier.vertical.datum
        ]
        if len(matches) != 1:
            raise VerticalCompatibilityError(
                f"surfaces are on {earlier.vertical.datum.value} and "
                f"{later.vertical.datum.value} and exactly one certified transform is required"
            )
        offset = matches[0].offset_m
        authority = matches[0].authority
        transform_unc = matches[0].uncertainty_m

    both = earlier.valid & later.valid
    delta = np.where(both, later.values + offset - earlier.values, np.nan)
    ua, ub = earlier.uncertainty_array(), later.uncertainty_array()
    unc = None
    detectable = None
    if ua is not None and ub is not None and transform_unc is not None:
        unc = np.where(
            both, np.sqrt(ua * ua + ub * ub + transform_unc * transform_unc), np.nan
        )
        detectable = np.where(both, np.abs(delta) > coverage_factor * unc, False)
    either = None
    if earlier.interpolated is not None or later.interpolated is not None:
        ia = (
            earlier.interpolated
            if earlier.interpolated is not None
            else np.zeros(earlier.shape, bool)
        )
        ib = (
            later.interpolated
            if later.interpolated is not None
            else np.zeros(later.shape, bool)
        )
        either = (ia | ib) & both
    return SurfaceDifference(
        delta_m=delta,
        uncertainty_m=unc,
        detectable=detectable,
        transform_authority=authority,
        compared_cells=int(both.sum()),
        either_interpolated=either,
    )
