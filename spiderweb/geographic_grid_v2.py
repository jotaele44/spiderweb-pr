"""Authoritative projected Puerto Rico federation grid V2.

Spiderweb owns this geometry contract. V1 remains unchanged and pixel-derived.
V2 is a projected square-cell hierarchy in EPSG:6566 with one fixed origin and
four exactly nested levels. Provider/source CRS never participates in Cell_ID
derivation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Iterator, Mapping

GRID_ID = "PR_GRID_GEOGRAPHIC_V2"
GRID_VERSION = "2.0.0-rc1"
CRS = "EPSG:6566"
ORIGIN_X = 12_000
ORIGIN_Y = 180_000
EXTENT_X_MIN = 12_000
EXTENT_Y_MIN = 180_000
EXTENT_X_MAX = 354_000
EXTENT_Y_MAX = 314_000
GENERATOR_VERSION = "pr-grid-geographic-v2/rc1"

LEVEL_RESOLUTION_M = {"L0": 2_000, "L1": 1_000, "L2": 500, "L3": 250}
LEVEL_ORDER = ("L0", "L1", "L2", "L3")
ROW_WIDTH = 3
COLUMN_WIDTH = 4
_CELL_ID_RE = re.compile(
    rf"^PRG2:(L[0-3]):R([0-9]{{{ROW_WIDTH}}}):C([0-9]{{{COLUMN_WIDTH}}})$"
)


class GridV2Error(ValueError):
    """Raised when a V2 invariant or compatibility gate fails."""


class BoundaryState(str, Enum):
    INTERIOR = "INTERIOR"
    EDGE_SHARED = "EDGE_SHARED"
    CORNER_SHARED = "CORNER_SHARED"
    OUTSIDE = "OUTSIDE"
    UNRESOLVED = "UNRESOLVED"


class NullState(str, Enum):
    NO_DATA = "NO_DATA"
    ZERO_RECORDS = "ZERO_RECORDS"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


@dataclass(frozen=True)
class GridLevel:
    name: str
    resolution_m: int
    rows: int
    columns: int

    @property
    def cell_count(self) -> int:
        return self.rows * self.columns


@dataclass(frozen=True)
class Cell:
    level: str
    row: int
    column: int

    @property
    def cell_id(self) -> str:
        return make_cell_id(self.level, self.row, self.column)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        size = level_spec(self.level).resolution_m
        xmin = ORIGIN_X + self.column * size
        ymin = ORIGIN_Y + self.row * size
        return xmin, ymin, xmin + size, ymin + size

    @property
    def area_m2(self) -> int:
        size = level_spec(self.level).resolution_m
        return size * size


@dataclass(frozen=True)
class PointBinding:
    state: BoundaryState
    cell_ids: tuple[str, ...]


def _level_dimensions(resolution_m: int) -> tuple[int, int]:
    width = EXTENT_X_MAX - EXTENT_X_MIN
    height = EXTENT_Y_MAX - EXTENT_Y_MIN
    if width % resolution_m or height % resolution_m:
        raise GridV2Error(f"extent is not divisible by {resolution_m} m")
    return height // resolution_m, width // resolution_m


LEVELS = {
    name: GridLevel(name, size, *_level_dimensions(size))
    for name, size in LEVEL_RESOLUTION_M.items()
}


def level_spec(level: str) -> GridLevel:
    try:
        return LEVELS[level]
    except KeyError as exc:
        raise GridV2Error(f"unknown grid level: {level!r}") from exc


def make_cell_id(level: str, row: int, column: int) -> str:
    spec = level_spec(level)
    if not (0 <= row < spec.rows and 0 <= column < spec.columns):
        raise GridV2Error(
            f"cell out of range for {level}: row={row}, column={column}"
        )
    return f"PRG2:{level}:R{row:0{ROW_WIDTH}d}:C{column:0{COLUMN_WIDTH}d}"


def parse_cell_id(value: str) -> Cell:
    match = _CELL_ID_RE.fullmatch(value)
    if not match:
        raise GridV2Error(f"malformed V2 Cell_ID: {value!r}")
    level, row_text, col_text = match.groups()
    cell = Cell(level, int(row_text), int(col_text))
    if cell.cell_id != value:
        raise GridV2Error(f"non-canonical V2 Cell_ID: {value!r}")
    return cell


def iter_cells(level: str) -> Iterator[Cell]:
    spec = level_spec(level)
    for row in range(spec.rows):
        for column in range(spec.columns):
            yield Cell(level, row, column)


def parent(cell: Cell) -> Cell | None:
    idx = LEVEL_ORDER.index(cell.level)
    if idx == 0:
        return None
    return Cell(LEVEL_ORDER[idx - 1], cell.row // 2, cell.column // 2)


def children(cell: Cell) -> tuple[Cell, Cell, Cell, Cell]:
    idx = LEVEL_ORDER.index(cell.level)
    if idx == len(LEVEL_ORDER) - 1:
        raise GridV2Error("L3 cells have no V2 child level")
    child_level = LEVEL_ORDER[idx + 1]
    return tuple(
        Cell(child_level, cell.row * 2 + dr, cell.column * 2 + dc)
        for dr, dc in ((0, 0), (0, 1), (1, 0), (1, 1))
    )


def neighbors(cell: Cell, *, diagonals: bool = False) -> tuple[Cell, ...]:
    spec = level_spec(cell.level)
    offsets = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    if diagonals:
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    found = []
    for dr, dc in offsets:
        row, column = cell.row + dr, cell.column + dc
        if 0 <= row < spec.rows and 0 <= column < spec.columns:
            found.append(Cell(cell.level, row, column))
    return tuple(found)


def validate_crs(crs: str | None) -> None:
    if crs is None or not str(crs).strip():
        raise GridV2Error("missing CRS")
    if str(crs).upper() != CRS:
        raise GridV2Error(f"wrong CRS: expected {CRS}, got {crs}")


def assert_compatibility(
    *,
    grid_id: str,
    grid_version: str,
    grid_manifest_sha256: str,
    expected_manifest_sha256: str,
) -> None:
    if grid_id != GRID_ID:
        raise GridV2Error(f"wrong Grid_ID: {grid_id}")
    if grid_version != GRID_VERSION:
        raise GridV2Error(f"wrong Grid_Version: {grid_version}")
    if grid_manifest_sha256 != expected_manifest_sha256:
        raise GridV2Error("GRID_MANIFEST_SHA256 mismatch")


def validate_null_state(value: str) -> NullState:
    try:
        return NullState(value)
    except ValueError as exc:
        raise GridV2Error(f"unknown null/data state: {value!r}") from exc


def _decimal(value: int | float | str | Decimal) -> Decimal:
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GridV2Error(f"invalid coordinate: {value!r}") from exc


def bind_point(
    x: int | float | str | Decimal,
    y: int | float | str | Decimal,
    *,
    level: str,
    crs: str | None,
) -> PointBinding:
    validate_crs(crs)
    spec = level_spec(level)
    xx, yy = _decimal(x), _decimal(y)
    xmin, ymin = Decimal(EXTENT_X_MIN), Decimal(EXTENT_Y_MIN)
    xmax, ymax = Decimal(EXTENT_X_MAX), Decimal(EXTENT_Y_MAX)
    if xx < xmin or xx > xmax or yy < ymin or yy > ymax:
        return PointBinding(BoundaryState.OUTSIDE, ())

    size = Decimal(spec.resolution_m)
    qx = (xx - xmin) / size
    qy = (yy - ymin) / size
    on_x = qx == qx.to_integral_value()
    on_y = qy == qy.to_integral_value()

    col_index = int(qx)
    row_index = int(qy)
    cols = (col_index - 1, col_index) if on_x else (col_index,)
    rows = (row_index - 1, row_index) if on_y else (row_index,)
    candidates = {
        (row, col)
        for row in rows
        for col in cols
        if 0 <= row < spec.rows and 0 <= col < spec.columns
    }

    if not candidates:
        return PointBinding(BoundaryState.OUTSIDE, ())
    if on_x and on_y and len(candidates) > 1:
        state = BoundaryState.CORNER_SHARED
    elif (on_x or on_y) and len(candidates) > 1:
        state = BoundaryState.EDGE_SHARED
    else:
        state = BoundaryState.INTERIOR

    ids = tuple(make_cell_id(level, row, col) for row, col in sorted(candidates))
    return PointBinding(state, ids)


def canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest_sha256(manifest: Mapping[str, object]) -> str:
    payload = dict(manifest)
    payload.pop("Grid_Manifest_SHA256", None)
    return sha256_bytes(canonical_json_bytes(payload))


def write_level_csv(level: str, destination: Path) -> tuple[int, str]:
    """Materialize the complete deterministic index for one hierarchy level."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    header = [
        "Grid_ID",
        "Grid_Version",
        "Grid_Level",
        "Cell_ID",
        "Row_Index",
        "Column_Index",
        "X_Min",
        "Y_Min",
        "X_Max",
        "Y_Max",
        "Area_m2",
        "CRS",
    ]
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        digest.update((",".join(header) + "\n").encode("utf-8"))
        for cell in iter_cells(level):
            xmin, ymin, xmax, ymax = cell.bounds
            values = [
                GRID_ID,
                GRID_VERSION,
                level,
                cell.cell_id,
                str(cell.row),
                str(cell.column),
                str(xmin),
                str(ymin),
                str(xmax),
                str(ymax),
                str(cell.area_m2),
                CRS,
            ]
            line = ",".join(values) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
            count += 1
    return count, digest.hexdigest()


def expected_full_counts() -> dict[str, int]:
    return {name: LEVELS[name].cell_count for name in LEVEL_ORDER}
