"""Canonical resolution between WGS84 geography and federation Cell_IDs.

Spiderweb is the federation's GEOMETRY_AUTHORITY. This module is the single
place where a coordinate, bounding box, or polygon becomes a ``Cell_ID``, so
spatial membership is computed once and every other repository stores and joins
on the resulting identifier rather than repeating geometry work.

The grid is a regular 256x384 lattice over a rendered canvas, so resolution is
O(1) arithmetic on the certified transform. No R-tree, GeoParquet or spatial
database is required at this scale, and none is used.

Two invariants hold regardless of data:

* A ``Cell_ID`` is a *spatial address*, never an identity claim. Records sharing
  a cell are co-located, not the same entity. Results therefore carry
  ``CANDIDATE_NOT_IDENTITY``, matching the Hub's federation spatial contract.
* Classification never gates existence. All 98,304 cells are valid addresses,
  including the 96,339 classified ``Water_or_Empty`` -- the archipelago's marine
  and insular-shelf cells are the point, not noise.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSFORM_PATH = REPO_ROOT / "registry/spatial/geometry/pr_grid_transform.json"

GRID_ROWS = 256
GRID_COLUMNS = 384
CELL_PX = 4
CELL_COUNT = GRID_ROWS * GRID_COLUMNS

IDENTITY_DEFAULT = "CANDIDATE_NOT_IDENTITY"


class SpatialResolverError(ValueError):
    """Raised when resolution is attempted without a usable transform."""


def cell_id(row_index: int, column_index: int) -> str:
    """Canonical unpadded address. One lexical form only, repo-wide."""
    if not (0 <= row_index < GRID_ROWS and 0 <= column_index < GRID_COLUMNS):
        raise SpatialResolverError(f"cell out of range: R{row_index}_C{column_index}")
    return f"R{row_index}_C{column_index}"


def parse_cell_id(value: str) -> tuple[int, int]:
    if not value.startswith("R") or "_C" not in value:
        raise SpatialResolverError(f"malformed Cell_ID: {value!r}")
    row_text, _, column_text = value[1:].partition("_C")
    # Reject zero-padded or otherwise non-canonical spellings outright: two
    # spellings of one address would silently split every cross-repo join.
    for text in (row_text, column_text):
        if not text.isdigit() or (len(text) > 1 and text[0] == "0"):
            raise SpatialResolverError(f"non-canonical Cell_ID: {value!r}")
    row_index, column_index = int(row_text), int(column_text)
    if not (0 <= row_index < GRID_ROWS and 0 <= column_index < GRID_COLUMNS):
        raise SpatialResolverError(f"Cell_ID out of range: {value!r}")
    return row_index, column_index


@dataclass(frozen=True)
class GridTransform:
    lon0: float
    lat0: float
    deg_per_px_x: float
    deg_per_px_y: float
    certification_state: str
    geometry_version: str
    grid_version: str

    @classmethod
    def load(cls, path: Path = TRANSFORM_PATH) -> "GridTransform":
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SpatialResolverError(f"no usable grid transform at {path}: {exc}") from exc
        transform = record["transform"]
        return cls(
            lon0=float(transform["lon0"]),
            lat0=float(transform["lat0"]),
            deg_per_px_x=float(transform["deg_per_px_x"]),
            deg_per_px_y=float(transform["deg_per_px_y"]),
            certification_state=str(record.get("certification_state", "PROVISIONAL")),
            geometry_version=str(record.get("geometry_version", "")),
            grid_version=str(record.get("grid_version", "")),
        )

    @property
    def deg_per_cell_x(self) -> float:
        return self.deg_per_px_x * CELL_PX

    @property
    def deg_per_cell_y(self) -> float:
        return self.deg_per_px_y * CELL_PX

    def cell_bounds(self, row_index: int, column_index: int) -> tuple[float, float, float, float]:
        """``(west, south, east, north)`` in WGS84 degrees."""
        west = self.lon0 + column_index * self.deg_per_cell_x
        north = self.lat0 - row_index * self.deg_per_cell_y
        return (west, north - self.deg_per_cell_y, west + self.deg_per_cell_x, north)

    def cell_centroid(self, row_index: int, column_index: int) -> tuple[float, float]:
        west, south, east, north = self.cell_bounds(row_index, column_index)
        return ((west + east) / 2.0, (south + north) / 2.0)

    def canvas_bounds(self) -> tuple[float, float, float, float]:
        return (
            self.lon0,
            self.lat0 - GRID_ROWS * self.deg_per_cell_y,
            self.lon0 + GRID_COLUMNS * self.deg_per_cell_x,
            self.lat0,
        )

    def locate(self, lon: float, lat: float) -> tuple[int, int] | None:
        """Row/column containing a coordinate, or ``None`` if off-canvas."""
        column_index = int((lon - self.lon0) // self.deg_per_cell_x)
        row_index = int((self.lat0 - lat) // self.deg_per_cell_y)
        if 0 <= row_index < GRID_ROWS and 0 <= column_index < GRID_COLUMNS:
            return row_index, column_index
        return None


def cell_set_sha256(cell_ids: Iterable[str]) -> str:
    """Content address of a cell set: sha256 over the sorted, canonical members."""
    ordered = sorted(set(cell_ids), key=parse_cell_id)
    payload = "\n".join(ordered).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class CellSet:
    cell_ids: tuple[str, ...]
    cell_set_sha256: str
    boundary_cells: tuple[str, ...]
    interior_cells: tuple[str, ...]
    certification_state: str
    identity_default: str = IDENTITY_DEFAULT

    @property
    def member_count(self) -> int:
        return len(self.cell_ids)

    @property
    def cell_set_id(self) -> str:
        return f"CS_{self.cell_set_sha256[:16]}"

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_set_id": self.cell_set_id,
            "cell_set_sha256": self.cell_set_sha256,
            "member_count": self.member_count,
            "member_cell_ids": list(self.cell_ids),
            "boundary_cells": list(self.boundary_cells),
            "interior_cells": list(self.interior_cells),
            "certification_state": self.certification_state,
            "identity_default": self.identity_default,
        }


def _build_cell_set(
    members: Sequence[tuple[int, int]], transform: GridTransform
) -> CellSet:
    member_lookup = set(members)
    boundary: list[str] = []
    interior: list[str] = []
    for row_index, column_index in sorted(member_lookup):
        neighbours = (
            (row_index - 1, column_index),
            (row_index + 1, column_index),
            (row_index, column_index - 1),
            (row_index, column_index + 1),
        )
        target = interior if all(n in member_lookup for n in neighbours) else boundary
        target.append(cell_id(row_index, column_index))
    ordered = sorted(member_lookup)
    ids = tuple(cell_id(r, c) for r, c in ordered)
    return CellSet(
        cell_ids=ids,
        cell_set_sha256=cell_set_sha256(ids),
        boundary_cells=tuple(boundary),
        interior_cells=tuple(interior),
        certification_state=transform.certification_state,
    )


def resolve_point(lon: float, lat: float, transform: GridTransform | None = None) -> CellSet:
    transform = transform or GridTransform.load()
    located = transform.locate(lon, lat)
    return _build_cell_set([located] if located else [], transform)


def resolve_bbox(
    bbox: Sequence[float], transform: GridTransform | None = None
) -> CellSet:
    """Resolve ``(west, south, east, north)`` to every intersecting cell."""
    transform = transform or GridTransform.load()
    west, south, east, north = bbox
    if west > east or south > north:
        raise SpatialResolverError(f"degenerate bbox: {tuple(bbox)}")

    first_column = int((west - transform.lon0) // transform.deg_per_cell_x)
    last_column = int((east - transform.lon0) // transform.deg_per_cell_x)
    first_row = int((transform.lat0 - north) // transform.deg_per_cell_y)
    last_row = int((transform.lat0 - south) // transform.deg_per_cell_y)

    members = [
        (row_index, column_index)
        for row_index in range(max(0, first_row), min(GRID_ROWS - 1, last_row) + 1)
        for column_index in range(max(0, first_column), min(GRID_COLUMNS - 1, last_column) + 1)
    ]
    return _build_cell_set(members, transform)


def _point_in_ring(lon: float, lat: float, ring: Sequence[Sequence[float]]) -> bool:
    """Ray casting. Boundary-exact behaviour is not required at cell scale."""
    inside = False
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        if (y1 > lat) != (y2 > lat):
            crossing = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if crossing > lon:
                inside = not inside
    return inside


def _polygon_rings(geometry: dict) -> list[list[Sequence[float]]]:
    kind = geometry.get("type")
    if kind == "Polygon":
        return [list(ring) for ring in geometry["coordinates"]]
    if kind == "MultiPolygon":
        return [list(ring) for polygon in geometry["coordinates"] for ring in polygon]
    raise SpatialResolverError(f"unsupported geometry type: {kind!r}")


def resolve_polygon(geometry: dict, transform: GridTransform | None = None) -> CellSet:
    """Resolve a GeoJSON Polygon/MultiPolygon by cell-centroid containment."""
    transform = transform or GridTransform.load()
    rings = _polygon_rings(geometry)
    outer_rings = [ring for ring in rings if len(ring) >= 3]
    if not outer_rings:
        raise SpatialResolverError("polygon has no usable ring")

    xs = [point[0] for ring in outer_rings for point in ring]
    ys = [point[1] for ring in outer_rings for point in ring]
    candidates = resolve_bbox((min(xs), min(ys), max(xs), max(ys)), transform)

    members: list[tuple[int, int]] = []
    for candidate in candidates.cell_ids:
        row_index, column_index = parse_cell_id(candidate)
        lon, lat = transform.cell_centroid(row_index, column_index)
        if sum(_point_in_ring(lon, lat, ring) for ring in outer_rings) % 2 == 1:
            members.append((row_index, column_index))
    return _build_cell_set(members, transform)


def resolve_cell(value: str, transform: GridTransform | None = None) -> CellSet:
    transform = transform or GridTransform.load()
    return _build_cell_set([parse_cell_id(value)], transform)


def resolve_cell_set(
    cell_ids: Iterable[str], transform: GridTransform | None = None
) -> CellSet:
    transform = transform or GridTransform.load()
    return _build_cell_set([parse_cell_id(value) for value in cell_ids], transform)
