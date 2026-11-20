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
ADMIN_METHOD = "ADMINISTRATIVE_SET"
DERIVED_METHOD = "DERIVED_SET"
ADMIN_UNCERTAINTY = "ADMINISTRATIVE_ONLY"
DERIVED_UNCERTAINTY = "DERIVED"
ADMIN_EVIDENCE_STATE = "VERIFIED_ADMINISTRATIVE_GEOMETRY"
DERIVED_EVIDENCE_STATE = "VERIFIED_DERIVED_GEOMETRY"
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

    q_min_col = (minx - EXTENT_X_MIN) / size
    q_max_col = (maxx - EXTENT_X_MIN) / size
    q_min_row = (miny - EXTENT_Y_MIN) / size
    q_max_row = (maxy - EXTENT_Y_MIN) / size

    raw_min_col = math.floor(q_min_col)
    raw_min_row = math.floor(q_min_row)
    # If the geometry begins exactly on an internal boundary, include the cell
    # on the lower side as a candidate. Positive-measure filtering below will
    # discard polygon touch-only contacts while retaining boundary-coincident
    # line segments in both scientifically shared cells.
    if raw_min_col > 0 and math.isclose(q_min_col, round(q_min_col), abs_tol=1e-12):
        raw_min_col -= 1
    if raw_min_row > 0 and math.isclose(q_min_row, round(q_min_row), abs_tol=1e-12):
        raw_min_row -= 1

    min_col = max(0, raw_min_col)
    max_col = min(spec.columns - 1, math.floor(q_max_col))
    min_row = max(0, raw_min_row)
    max_row = min(spec.rows - 1, math.floor(q_max_row))

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


@dataclass(frozen=True)
class SetGeometryRecord:
    repository: str
    record_id: str
    geometry: BaseGeometry
    crs: str
    spatial_role: str
    binding_method: str
    uncertainty_class: str
    evidence_state: str


@dataclass(frozen=True)
class SetBindingResult:
    repository: str
    record_id: str
    level: str
    binding_method: str
    uncertainty_class: str
    evidence_state: str
    geometry_type: str
    bindings: tuple[dict[str, Any], ...]


def set_geometry_from_mapping(row: Mapping[str, Any]) -> SetGeometryRecord:
    """Parse one evidence-gated administrative or derived set geometry."""
    repository = _require_text("Repository", row.get("Repository"))
    record_id = _require_text("Record_ID", row.get("Record_ID"))
    method = row.get("Binding_Method")
    uncertainty = row.get("Uncertainty_Class")
    evidence = row.get("Geometry_Evidence_State")

    expected = {
        ADMIN_METHOD: (ADMIN_UNCERTAINTY, ADMIN_EVIDENCE_STATE, "ADMINISTRATIVE_EXTENT"),
        DERIVED_METHOD: (DERIVED_UNCERTAINTY, DERIVED_EVIDENCE_STATE, "DERIVED_EXTENT"),
    }
    if method not in expected:
        raise GridV2Error(
            "set geometry Binding_Method must be ADMINISTRATIVE_SET or DERIVED_SET"
        )
    expected_uncertainty, expected_evidence, default_role = expected[str(method)]
    if uncertainty != expected_uncertainty:
        raise GridV2Error(
            f"{method} requires Uncertainty_Class={expected_uncertainty}"
        )
    if evidence != expected_evidence:
        raise GridV2Error(
            f"{method} requires Geometry_Evidence_State={expected_evidence}"
        )

    spatial_role = _require_text("Spatial_Role", row.get("Spatial_Role", default_role))
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
    except Exception as exc:
        raise GridV2Error(f"invalid GeoJSON geometry: {exc}") from exc
    geometry = _validate_geometry(geometry, {"Polygon", "MultiPolygon"})

    return SetGeometryRecord(
        repository=repository,
        record_id=record_id,
        geometry=geometry,
        crs=crs,
        spatial_role=spatial_role,
        binding_method=str(method),
        uncertainty_class=str(uncertainty),
        evidence_state=str(evidence),
    )


def bind_set_geometry(
    record: SetGeometryRecord,
    *,
    level: str,
) -> SetBindingResult:
    """Bind a non-exact administrative/derived polygon to positive-area cells."""
    level_spec(level)
    if record.crs != CRS:
        raise GridV2Error(f"wrong CRS: expected {CRS}, got {record.crs}")

    expected = {
        ADMIN_METHOD: (ADMIN_UNCERTAINTY, ADMIN_EVIDENCE_STATE),
        DERIVED_METHOD: (DERIVED_UNCERTAINTY, DERIVED_EVIDENCE_STATE),
    }
    if record.binding_method not in expected:
        raise GridV2Error("unsupported set binding method")
    expected_uncertainty, expected_evidence = expected[record.binding_method]
    if record.uncertainty_class != expected_uncertainty:
        raise GridV2Error("binding method and uncertainty class disagree")
    if record.evidence_state != expected_evidence:
        raise GridV2Error("binding method and evidence state disagree")

    geometry = _validate_geometry(record.geometry, {"Polygon", "MultiPolygon"})
    cell_area = float(level_spec(level).resolution_m ** 2)
    rows: list[dict[str, Any]] = []
    for row, column, cell_geometry in _candidate_cells(geometry, level=level):
        intersection = geometry.intersection(cell_geometry)
        overlap = float(intersection.area)
        if overlap <= MEASURE_EPSILON:
            continue
        rows.append(
            {
                "Grid_ID": GRID_ID,
                "Grid_Version": GRID_VERSION,
                "Grid_Level": level,
                "Repository": record.repository,
                "Record_ID": record.record_id,
                "Cell_ID": make_cell_id(level, row, column),
                "Spatial_Role": record.spatial_role,
                "Binding_Method": record.binding_method,
                "Uncertainty_Class": record.uncertainty_class,
                # For set membership this compatibility field denotes a realized
                # positive-area relation, not an exact point claim.
                "Binding_State": "INTERIOR",
                "Overlap_Area_m2": overlap,
                "Cell_Coverage_Fraction": overlap / cell_area,
                "Length_In_Cell_m": None,
                "Binding_Version": BINDING_SCHEMA_VERSION,
                "Geometry_State": record.evidence_state,
                # Deliberately null: the set is evidence-qualified but does not
                # assert exact positional confidence for the underlying record.
                "Confidence": None,
            }
        )

    rows.sort(key=lambda value: value["Cell_ID"])
    return SetBindingResult(
        repository=record.repository,
        record_id=record.record_id,
        level=level,
        binding_method=record.binding_method,
        uncertainty_class=record.uncertainty_class,
        evidence_state=record.evidence_state,
        geometry_type=geometry.geom_type,
        bindings=tuple(rows),
    )


def bind_set_geometries(
    rows: Iterable[Mapping[str, Any]],
    *,
    level: str,
) -> tuple[SetBindingResult, ...]:
    """Bind a denominator of administrative/derived sets with duplicate rejection."""
    level_spec(level)
    results: list[SetBindingResult] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        record = set_geometry_from_mapping(row)
        key = (record.repository, record.record_id)
        if key in seen:
            raise GridV2Error(
                f"duplicate set-geometry record identity: {record.repository}/{record.record_id}"
            )
        seen.add(key)
        results.append(bind_set_geometry(record, level=level))
    return tuple(results)


def flatten_set_binding_rows(
    results: Iterable[SetBindingResult],
) -> list[dict[str, Any]]:
    return [binding for result in results for binding in result.bindings]


def set_binding_receipt(
    results: Iterable[SetBindingResult],
) -> dict[str, Any]:
    materialized = tuple(results)
    method_counts: dict[str, int] = {}
    uncertainty_counts: dict[str, int] = {}
    evidence_counts: dict[str, int] = {}
    zero_binding_records = 0
    row_count = 0

    for result in materialized:
        method_counts[result.binding_method] = method_counts.get(result.binding_method, 0) + 1
        uncertainty_counts[result.uncertainty_class] = (
            uncertainty_counts.get(result.uncertainty_class, 0) + 1
        )
        evidence_counts[result.evidence_state] = (
            evidence_counts.get(result.evidence_state, 0) + 1
        )
        if not result.bindings:
            zero_binding_records += 1
        row_count += len(result.bindings)

    return {
        "contract": "pr-grid-v2-set-binding-receipt/1.0",
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "CRS": CRS,
        "Binding_Schema_Version": BINDING_SCHEMA_VERSION,
        "Migration_Provenance_Class": "RECOMPUTED_FROM_SOURCE_GEOMETRY",
        "Input_Record_Count": len(materialized),
        "Binding_Row_Count": row_count,
        "Zero_Binding_Record_Count": zero_binding_records,
        "Binding_Method_Record_Counts": dict(sorted(method_counts.items())),
        "Uncertainty_Class_Record_Counts": dict(sorted(uncertainty_counts.items())),
        "Geometry_Evidence_State_Record_Counts": dict(sorted(evidence_counts.items())),
        "Exact_Cell_Claim_Permitted": False,
    }
