"""Transects and vertical cross-sections across the land-sea boundary.

A cross-section samples each surface along one line and keeps each surface on
its own vertical reference.  The surfaces are moved onto a common vertical
axis only when :func:`spiderweb.access_points.vertical.decide_join` allows it.

Nothing is interpolated between surfaces.  Where no survey covers the line,
the section has a gap, and the gap is reported with its length.  A continuous
land-to-sea profile is never manufactured across ground nobody measured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .raster import GridMismatchError, NotAnElevationSurfaceError, SurfaceGrid
from .vertical import (
    CertifiedTransform,
    JoinDecision,
    JoinState,
    VerticalDatum,
    combined_uncertainty_m,
    decide_join,
)

TRANSECT_VERSION = "access-point-transect/1.0"


@dataclass(frozen=True, slots=True)
class TransectSample:
    distance_m: float
    xy: tuple[float, float]
    elevation_m: float | None  # positive up, on ``datum``; None = no data here
    uncertainty_m: float | None
    interpolated: bool | None


@dataclass(frozen=True)
class SurfaceProfile:
    """One surface sampled along the line, on its own datum."""

    source_id: str | None
    kind: str
    datum: VerticalDatum
    samples: tuple[TransectSample, ...]

    @property
    def covered_fraction(self) -> float:
        if not self.samples:
            return 0.0
        return sum(1 for s in self.samples if s.elevation_m is not None) / len(self.samples)


@dataclass(frozen=True, slots=True)
class Gap:
    start_m: float
    end_m: float

    @property
    def length_m(self) -> float:
        return self.end_m - self.start_m


@dataclass(frozen=True)
class CrossSection:
    line_xy: tuple[tuple[float, float], ...]
    crs: str
    spacing_m: float
    length_m: float
    profiles: tuple[SurfaceProfile, ...]
    join: JoinDecision | None
    common_datum: VerticalDatum | None
    common_profiles: tuple[SurfaceProfile, ...]
    gaps: tuple[Gap, ...]

    @property
    def is_continuous(self) -> bool:
        """True only if every station is covered by at least one surface."""

        return not self.gaps


def _stations(
    grid: SurfaceGrid, line_xy: Sequence[tuple[float, float]], spacing_m: float
) -> tuple[list[float], list[tuple[float, float]], float]:
    """Stations along the line.  Distances are ground metres."""

    sx = grid.cell_size_m[0] / grid.cell_size_crs[0]
    sy = grid.cell_size_m[1] / grid.cell_size_crs[1]
    distances: list[float] = [0.0]
    points: list[tuple[float, float]] = [tuple(map(float, line_xy[0]))]  # type: ignore[list-item]
    travelled = 0.0
    carry = 0.0
    for (x0, y0), (x1, y1) in zip(line_xy, line_xy[1:]):
        seg = math.hypot((x1 - x0) * sx, (y1 - y0) * sy)
        if seg <= 0:
            continue
        position = spacing_m - carry
        while position <= seg + 1e-9:
            t = min(position / seg, 1.0)
            distances.append(travelled + position)
            points.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
            position += spacing_m
        carry = seg - (position - spacing_m)
        travelled += seg
    if travelled <= 0:
        raise ValueError("the transect line has no length")
    if travelled - distances[-1] > 1e-6:
        distances.append(travelled)
        points.append(tuple(map(float, line_xy[-1])))  # type: ignore[arg-type]
    return distances, points, travelled


def sample_profile(
    grid: SurfaceGrid, distances: Sequence[float], points: Sequence[tuple[float, float]]
) -> SurfaceProfile:
    """Read the cell under each station.  No resampling, no smoothing."""

    if not grid.is_elevation:
        raise NotAnElevationSurfaceError(
            f"{grid.kind.value} is not a height surface and cannot be profiled"
        )
    assert grid.vertical is not None
    unc = grid.uncertainty_array()
    rows, cols = grid.shape
    samples: list[TransectSample] = []
    for distance, (x, y) in zip(distances, points):
        col = math.floor((x - grid.origin[0]) / grid.cell_size_crs[0])
        row = math.floor((grid.origin[1] - y) / grid.cell_size_crs[1])
        value = None
        sigma = None
        interp = None
        if 0 <= row < rows and 0 <= col < cols:
            cell = float(grid.values[row, col])
            if math.isfinite(cell):
                value = cell
                if unc is not None and math.isfinite(float(unc[row, col])):
                    sigma = float(unc[row, col])
                if grid.interpolated is not None:
                    interp = bool(grid.interpolated[row, col])
        samples.append(TransectSample(float(distance), (float(x), float(y)), value, sigma, interp))
    return SurfaceProfile(grid.source_id, grid.kind.value, grid.vertical.datum, tuple(samples))


def _gaps(distances: Sequence[float], profiles: Sequence[SurfaceProfile]) -> tuple[Gap, ...]:
    covered = np.zeros(len(distances), dtype=bool)
    for profile in profiles:
        covered |= np.array([s.elevation_m is not None for s in profile.samples], dtype=bool)
    gaps: list[Gap] = []
    start: int | None = None
    for i, ok in enumerate(covered):
        if not ok and start is None:
            start = i
        if ok and start is not None:
            gaps.append(Gap(float(distances[start]), float(distances[i - 1])))
            start = None
    if start is not None:
        gaps.append(Gap(float(distances[start]), float(distances[-1])))
    return tuple(gaps)


def build_cross_section(
    surfaces: Sequence[SurfaceGrid],
    line_xy: Sequence[tuple[float, float]],
    *,
    spacing_m: float,
    transforms: Sequence[CertifiedTransform] = (),
    lon_lat: tuple[float, float] | None = None,
) -> CrossSection:
    """Sample one or more surfaces along a line.

    All surfaces must be in the same horizontal CRS; reproject explicitly
    beforehand.  With exactly two surfaces (conventionally land then sea) the
    result carries the join decision, and ``common_profiles`` is filled only
    when a difference between them is defensible.
    """

    if not surfaces:
        raise ValueError("at least one surface is required")
    if len(line_xy) < 2:
        raise ValueError("a transect needs at least two vertices")
    if not (math.isfinite(spacing_m) and spacing_m > 0):
        raise ValueError("spacing_m must be positive")
    crs = surfaces[0].crs
    for grid in surfaces:
        if grid.crs != crs:
            raise GridMismatchError(
                "surfaces are in different horizontal CRSs; reproject explicitly first"
            )
        if not math.isclose(
            grid.cell_size_m[0] / grid.cell_size_crs[0],
            surfaces[0].cell_size_m[0] / surfaces[0].cell_size_crs[0],
            rel_tol=1e-6,
        ):
            raise GridMismatchError("surfaces disagree about the ground size of a CRS unit")
    distances, points, length = _stations(surfaces[0], line_xy, spacing_m)
    profiles = tuple(sample_profile(grid, distances, points) for grid in surfaces)

    join: JoinDecision | None = None
    common_datum: VerticalDatum | None = None
    common: tuple[SurfaceProfile, ...] = ()
    if len(surfaces) == 2:
        land, sea = surfaces
        assert land.vertical is not None and sea.vertical is not None
        lon, lat = lon_lat if lon_lat is not None else (None, None)
        join = decide_join(
            land.vertical.to_reference(),
            sea.vertical.to_reference(),
            transforms=transforms,
            lon=lon,
            lat=lat,
        )
        if join.state is JoinState.SAME_REFERENCE:
            common_datum = join.common_datum
            common = profiles
        elif join.state is JoinState.TRANSFORMED:
            common_datum = join.common_datum
            transform = next(
                t
                for t in transforms
                if t.source is sea.vertical.datum
                and t.target is land.vertical.datum
                and t.covers(lon, lat)
            )
            moved = tuple(
                TransectSample(
                    s.distance_m,
                    s.xy,
                    None if s.elevation_m is None else s.elevation_m + transform.offset_m,
                    None
                    if s.elevation_m is None
                    else combined_uncertainty_m(s.uncertainty_m, transform.uncertainty_m),
                    s.interpolated,
                )
                for s in profiles[1].samples
            )
            assert common_datum is not None
            common = (
                profiles[0],
                SurfaceProfile(profiles[1].source_id, profiles[1].kind, common_datum, moved),
            )
    elif len({p.datum for p in profiles}) == 1:
        common_datum = profiles[0].datum
        common = profiles
    return CrossSection(
        line_xy=tuple((float(x), float(y)) for x, y in line_xy),
        crs=crs,
        spacing_m=float(spacing_m),
        length_m=float(length),
        profiles=profiles,
        join=join,
        common_datum=common_datum,
        common_profiles=common,
        gaps=_gaps(distances, profiles),
    )


def cross_section_to_dict(section: CrossSection, *, truth_kind: str) -> dict:
    """JSON form of a cross-section.  ``truth_kind`` states what the data is."""

    def profile(p: SurfaceProfile) -> dict:
        return {
            "source_id": p.source_id,
            "kind": p.kind,
            "datum": p.datum.value,
            "covered_fraction": p.covered_fraction,
            "samples": [
                {
                    "distance_m": s.distance_m,
                    "xy": [s.xy[0], s.xy[1]],
                    "elevation_m": s.elevation_m,
                    "uncertainty_m": s.uncertainty_m,
                    "interpolated": s.interpolated,
                }
                for s in p.samples
            ],
        }

    return {
        "schema": "access_point_cross_section/1.0",
        "transect_version": TRANSECT_VERSION,
        "truth_kind": truth_kind,
        "crs": section.crs,
        "line_xy": [[x, y] for x, y in section.line_xy],
        "spacing_m": section.spacing_m,
        "length_m": section.length_m,
        "is_continuous": section.is_continuous,
        "gaps": [
            {"start_m": g.start_m, "end_m": g.end_m, "length_m": g.length_m} for g in section.gaps
        ],
        "profiles": [profile(p) for p in section.profiles],
        "join": None
        if section.join is None
        else {
            "state": section.join.state.value,
            "common_datum": None if section.join.common_datum is None else section.join.common_datum.value,
            "authority": section.join.authority,
            "reason": section.join.reason,
            "may_difference": section.join.may_difference,
        },
        "common_datum": None if section.common_datum is None else section.common_datum.value,
        "common_profiles": [profile(p) for p in section.common_profiles],
        "vertical_axis": "elevation in metres, positive up, each profile on its own datum",
    }
