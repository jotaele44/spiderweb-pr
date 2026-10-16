"""Authoritative positive-measure geometry bindings for PR grid V2.

This module extends the Spiderweb authority beyond point bindings without
changing the frozen V2 binding schema.

Supported deterministic slice:
- exact projected Polygon/MultiPolygon -> INTERSECTS_POSITIVE_AREA
- exact projected LineString/MultiLineString -> LINE_POSITIVE_LENGTH

Touch-only polygon contacts and zero-length line contacts never create binding
rows. Canonical geometry remains in Spiderweb; consumers receive only binding
rows and receipts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from spiderweb.geographic_grid_v2 import (
    CRS,
    EXTENT_X_MAX,
    EXTENT_X_MIN,
    EXTENT_Y_MAX,
    EXTENT_Y_MIN,
    GRID_ID,
    GRID_VERSION,
    GridV2Error,
    level_spec,
    make_cell_id,
)

BINDING_SCHEMA_VERSION = "pr-grid-v2-binding/1.0"
GRID_MANIFEST_SHA256 = "8902af188ad449955119016f5747fe2393c582d9ed552fb03bcaecd9ab510aa4"
UNCERTAINTY_CLASS = "EXACT"
POLYGON_METHOD = "INTERSECTS_POSITIVE_AREA"
LINE_METHOD = "LINE_POSITIVE_LENGTH"
POLYGON_GEOMETRY_STATE = "VERIFIED_PROJECTED_POLYGON"
LINE_GEOMETRY_STATE = "VERIFIED_PROJECTED_LINE"
MEASURE_EPSILON = 1e-9


@dataclass(frozen=True)
class ExactGeometryRecord:
    repository: str
    record_id: str
    geometry: BaseGeometry
    crs: str
    spatial_role: str
    uncertainty_class: str = UNCERTAINTY_CLASS


@dataclass(frozen=True)
class GeometryBindingResult:
    repository: str
    record_id: str
    level: str
    geometry_type: str
    bindings: tuple[dict[str, Any], ...]


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GridV2Error(f"{name} must be a non-empty string")
    return value.strip()


def _validate_geometry(geometry: BaseGeometry, allowed: set[str]) -> BaseGeometry:
    if geometry.is_empty:
        raise GridV2Error("geometry must not be empty")
    if geometry.geom_type not in allowed:
        expected = ", ".join(sorted(allowed))
        raise GridV2Error(
            f"unsupported geometry type {geometry.geom_type!r}; expected {expected}"
        )
    if not geometry.is_valid:
        raise GridV2Error("geometry must be valid")
    return geometry


def exact_geometry_from_mapping(row: Mapping[str, Any]) -> ExactGeometryRecord:
    repository = _require_text("Repository", row.get("Repository"))
    record_id = _require_text("Record_ID", row.get("Record_ID"))
    spatial_role = _require_text("Spatial_Role", row.get("Spatial_Role", "GEOMETRY"))

    uncertainty = row.get("Uncertainty_Class", UNCERTAINTY_CLASS)
    if uncertainty != UNCERTAINTY_CLASS:
        raise GridV2Error(
            "exact geometry V2 migration only accepts Uncertainty_Class='EXACT'"
        )

    crs = row.get("CRS")
    if crs != CRS:
        if not isinstance(crs, str) or not crs.strip():
            raise GridV2Error("missing CRS")
        raise GridV2Error(f"wrong CRS: expected {CRS}, got {crs}")

    raw_geometry = row.get("Geometry")
    if not isinstance(raw_geometry, Mapping):
        raise GridV2Error("Geometry must be a GeoJSON geometry object")
    try:
        geometry = shape(raw_geometry)
    except Exception as exc:  # shapely raises several parser exception types
        raise GridV2Error(f"invalid GeoJSON geometry: {exc}") from exc

    allowed = {
        "Polygon",
        "MultiPolygon",
        "LineString",
        "MultiLineString",
    }
    return ExactGeometryRecord(
        repository=repository,
        record_id=record_id,
        geometry=_validate_geometry(geometry, allowed),
        crs=crs,
        spatial_role=spatial_role,
        uncertainty_class=uncertainty,
    )


def _candidate_cells(geometry: BaseGeometry, *, level: str):
    spec = level_spec(level)
    size = spec.resolution_m
    minx, miny, maxx, maxy = geometry.bounds

    if (
        maxx < EXTENT_X_MIN
        or minx > EXTENT_X_MAX
        or maxy < EXTENT_Y_MIN
        or miny > EXTENT_Y_MAX
    ):
        return

    min_col = max(0, math.floor((minx - EXTENT_X_MIN) / size))
    max_col = min(spec.columns - 1, math.floor((maxx - EXTENT_X_MIN) / size))
    min_row = max(0, math.floor((miny - EXTENT_Y_MIN) / size))
    max_row = min(spec.rows - 1, math.floor((maxy - EXTENT_Y_MIN) / size))

    # A geometry whose maximum lies exactly on the outer grid edge can floor to
    # columns/rows == dimension; clamp above keeps the candidate denominator valid.
    for row in range(min_row, max_row + 1):
        ymin = EXTENT_Y_MIN + row * size
        ymax = ymin + size
        for column in range(min_col, max_col + 1):
            xmin = EXTENT_X_MIN + column * size
            xmax = xmin + size
            yield row, column, box(xmin, ymin, xmax, ymax)


def _base_row(
    record: ExactGeometryRecord,
    *,
    level: str,
    cell_id: str,
    binding_method: str,
    geometry_state: str,
) -> dict[str, Any]:
    return {
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "Grid_Level": level,
        "Repository": record.repository,
        "Record_ID": record.record_id,
        "Cell_ID": cell_id,
        "Spatial_Role": record.spatial_role,
        "Binding_Method": binding_method,
        "Uncertainty_Class": UNCERTAINTY_CLASS,
        # The frozen schema predates non-point relation states. For positive
        # measure geometry bindings INTERIOR means a realized cell relation;
        # Binding_Method and Geometry_State carry the exact predicate semantics.
        "Binding_State": "INTERIOR",
        "Overlap_Area_m2": None,
        "Cell_Coverage_Fraction": None,
        "Length_In_Cell_m": None,
        "Binding_Version": BINDING_SCHEMA_VERSION,
        "Geometry_State": geometry_state,
        "Confidence": 1.0,
    }


def bind_exact_polygon(
    record: ExactGeometryRecord,
    *,
    level: str,
) -> GeometryBindingResult:
    level_spec(level)
    if record.crs != CRS:
        raise GridV2Error(f"wrong CRS: expected {CRS}, got {record.crs}")
    geometry = _validate_geometry(record.geometry, {"Polygon", "MultiPolygon"})
    cell_area = float(level_spec(level).resolution_m ** 2)
    rows: list[dict[str, Any]] = []

    for row, column, cell_geometry in _candidate_cells(geometry, level=level):
        intersection = geometry.intersection(cell_geometry)
        overlap = float(intersection.area)
        if overlap <= MEASURE_EPSILON:
            continue
        binding = _base_row(
            record,
            level=level,
            cell_id=make_cell_id(level, row, column),
            binding_method=POLYGON_METHOD,
            geometry_state=POLYGON_GEOMETRY_STATE,
        )
        binding["Overlap_Area_m2"] = overlap
        binding["Cell_Coverage_Fraction"] = overlap / cell_area
        rows.append(binding)

    rows.sort(key=lambda value: value["Cell_ID"])
    return GeometryBindingResult(
        repository=record.repository,
        record_id=record.record_id,
        level=level,
        geometry_type=geometry.geom_type,
        bindings=tuple(rows),
    )


def bind_exact_line(
    record: ExactGeometryRecord,
    *,
    level: str,
) -> GeometryBindingResult:
    level_spec(level)
    if record.crs != CRS:
        raise GridV2Error(f"wrong CRS: expected {CRS}, got {record.crs}")
    geometry = _validate_geometry(record.geometry, {"LineString", "MultiLineString"})
    rows: list[dict[str, Any]] = []

    for row, column, cell_geometry in _candidate_cells(geometry, level=level):
        intersection = geometry.intersection(cell_geometry)
        length = float(intersection.length)
        if length <= MEASURE_EPSILON:
            continue
        binding = _base_row(
            record,
            level=level,
            cell_id=make_cell_id(level, row, column),
            binding_method=LINE_METHOD,
            geometry_state=LINE_GEOMETRY_STATE,
        )
        binding["Length_In_Cell_m"] = length
        rows.append(binding)

    rows.sort(key=lambda value: value["Cell_ID"])
    return GeometryBindingResult(
        repository=record.repository,
        record_id=record.record_id,
        level=level,
        geometry_type=geometry.geom_type,
        bindings=tuple(rows),
    )


def bind_exact_geometry(
    record: ExactGeometryRecord,
    *,
    level: str,
) -> GeometryBindingResult:
    if record.geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return bind_exact_polygon(record, level=level)
    if record.geometry.geom_type in {"LineString", "MultiLineString"}:
        return bind_exact_line(record, level=level)
    raise GridV2Error(f"unsupported geometry type: {record.geometry.geom_type}")


def bind_exact_geometries(
    rows: Iterable[Mapping[str, Any]],
    *,
    level: str,
) -> tuple[GeometryBindingResult, ...]:
    level_spec(level)
    results: list[GeometryBindingResult] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        record = exact_geometry_from_mapping(row)
        key = (record.repository, record.record_id)
        if key in seen:
            raise GridV2Error(
                f"duplicate exact-geometry record identity: {record.repository}/{record.record_id}"
            )
        seen.add(key)
        results.append(bind_exact_geometry(record, level=level))
    return tuple(results)


def flatten_geometry_binding_rows(
    results: Iterable[GeometryBindingResult],
) -> list[dict[str, Any]]:
    return [binding for result in results for binding in result.bindings]


def geometry_binding_receipt(
    results: Iterable[GeometryBindingResult],
) -> dict[str, Any]:
    materialized = tuple(results)
    method_counts: dict[str, int] = {}
    geometry_type_counts: dict[str, int] = {}
    zero_binding_records = 0
    row_count = 0
    for result in materialized:
        geometry_type_counts[result.geometry_type] = (
            geometry_type_counts.get(result.geometry_type, 0) + 1
        )
        if not result.bindings:
            zero_binding_records += 1
        for row in result.bindings:
            method = str(row["Binding_Method"])
            method_counts[method] = method_counts.get(method, 0) + 1
            row_count += 1

    return {
        "contract": "pr-grid-v2-exact-geometry-binding-receipt/1.0",
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "CRS": CRS,
        "Binding_Schema_Version": BINDING_SCHEMA_VERSION,
        "Migration_Provenance_Class": "RECOMPUTED_FROM_SOURCE_GEOMETRY",
        "Input_Record_Count": len(materialized),
        "Binding_Row_Count": row_count,
        "Zero_Binding_Record_Count": zero_binding_records,
        "Binding_Method_Counts": dict(sorted(method_counts.items())),
        "Geometry_Type_Counts": dict(sorted(geometry_type_counts.items())),
    }
