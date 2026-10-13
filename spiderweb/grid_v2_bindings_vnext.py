"""Provisional vNext authoritative projected geometry-to-cell bindings.

Independent from frozen RC1 point bindings. All geometry is supplied in
EPSG:6566, with EXACT source precision, and never repaired or reprojected.
Do not promote this provisional contract to consumers until certified.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from shapely.geometry import LineString, box, shape

from spiderweb.geographic_grid_v2 import (
    CRS, EXTENT_X_MAX, EXTENT_X_MIN, EXTENT_Y_MAX, EXTENT_Y_MIN,
    GRID_ID, GRID_VERSION, Cell, GridV2Error, bind_point, level_spec,
    validate_crs,
)
from spiderweb.grid_v2_bindings import GRID_MANIFEST_SHA256

BINDING_VERSION = "pr-grid-v2-binding/2.0.0-rc1"
BINDING_SCHEMA_SHA256 = "e3dbd844bd8c35451e112af6a8d39461b1490454e2f41e191133d8115980f2c8"
RC1_BINDING_SCHEMA_SHA256 = "dabc461e47134b3b150be9aeb23b3d0097563493b33b3187538255e06b16a022"
CONTRACT_STATE = "PROVISIONAL"
GRID_DOMAIN = box(EXTENT_X_MIN, EXTENT_Y_MIN, EXTENT_X_MAX, EXTENT_Y_MAX)
GEOMETRY_TYPES = {
    "Point": "POINT", "Polygon": "POLYGON", "MultiPolygon": "POLYGON",
    "LineString": "LINE", "MultiLineString": "LINE",
}


@dataclass(frozen=True)
class GeometryBindingResult:
    repository: str
    record_id: str
    source_geometry_type: str
    state: str
    bindings: tuple[dict[str, Any], ...]
    unique_clipped_length_m: float = 0.0
    clipped_area_m2: float = 0.0


def validate_schema_pins(root: Path | None = None) -> None:
    """Fail closed before materialization if any frozen or vNext pin drifts."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    schema = root / "schemas/pr_grid_geographic_v2_binding_vnext.schema.json"
    rc1 = root / "schemas/pr_grid_geographic_v2_binding.schema.json"
    manifest = root / "registry/spatial/v2/pr_grid_geographic_v2_binding_vnext.manifest.json"
    grid_manifest = root / "registry/spatial/v2/pr_grid_geographic_v2.manifest.json"
    for path in (schema, rc1, manifest, grid_manifest):
        if not path.is_file():
            raise GridV2Error(f"missing required contract file: {path}")
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(schema) != BINDING_SCHEMA_SHA256:
        raise GridV2Error("vNext binding schema SHA256 mismatch")
    if digest(rc1) != RC1_BINDING_SCHEMA_SHA256:
        raise GridV2Error("frozen RC1 binding schema SHA256 mismatch")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    gm = json.loads(grid_manifest.read_text(encoding="utf-8"))
    expected = {
        "Binding_Version": BINDING_VERSION,
        "Binding_Schema_SHA256": BINDING_SCHEMA_SHA256,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "RC1_Binding_Schema_SHA256": RC1_BINDING_SCHEMA_SHA256,
        "Certification_State": CONTRACT_STATE,
        "Consumer_Activation": "BLOCKED_UNTIL_CERTIFIED",
    }
    for key, value in expected.items():
        if m.get(key) != value:
            raise GridV2Error(f"vNext manifest mismatch: {key}")
    if (gm.get("Grid_Manifest_SHA256") != GRID_MANIFEST_SHA256 or
            gm.get("Binding_Schema_SHA256") != RC1_BINDING_SCHEMA_SHA256 or
            gm.get("Grid_ID") != GRID_ID or gm.get("Grid_Version") != GRID_VERSION):
        raise GridV2Error("frozen grid-manifest identity mismatch")


def _require_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GridV2Error(f"{key} must be non-empty text")
    return value.strip()


def _assert_xy_coordinates(value: Any) -> None:
    """Prevent silently discarded Z/M coordinates and non-finite values."""
    if not isinstance(value, (list, tuple)) or not value:
        raise GridV2Error("invalid/empty coordinate array")
    if isinstance(value[0], (float, int)):
        if len(value) != 2 or any(
            isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(v) for v in value
        ):
            raise GridV2Error("geometry requires finite 2D XY coordinates only")
        return
    for child in value:
        _assert_xy_coordinates(child)


def _parse_record(row: Mapping[str, Any]):
    repository, record_id = _require_text(row, "Repository"), _require_text(row, "Record_ID")
    role = _require_text({**row, "Spatial_Role": row.get("Spatial_Role", "GEOMETRY_FOOTPRINT")}, "Spatial_Role")
    validate_crs(row.get("CRS"))
    if row.get("Uncertainty_Class") != "EXACT":
        raise GridV2Error("vNext materialization requires EXACT positional precision")
    for key, expected in (("Grid_ID", GRID_ID), ("Grid_Version", GRID_VERSION),
                          ("Grid_Manifest_SHA256", GRID_MANIFEST_SHA256)):
        if key in row and row[key] != expected:
            raise GridV2Error(f"{key} mismatch")
    raw = row.get("Geometry")
    if not isinstance(raw, dict) or raw.get("type") not in GEOMETRY_TYPES:
        raise GridV2Error("unsupported geometry type; expected Point/Polygon/Line")
    if "coordinates" not in raw:
        raise GridV2Error("missing geometry coordinates")
    _assert_xy_coordinates(raw["coordinates"])
    if set(raw) - {"type", "coordinates"}:
        raise GridV2Error("unsupported GeoJSON geometry members")
    try:
        geom = shape(raw)
    except Exception as exc:
        raise GridV2Error("invalid GeoJSON geometry") from exc
    if geom.is_empty or not geom.is_valid or geom.has_z or getattr(geom, "has_m", False):
        raise GridV2Error("invalid, empty, or non-2D geometry")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return repository, record_id, role, GEOMETRY_TYPES[raw["type"]], geom, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_cells(bounds, level: str):
    """BBox is candidate discovery only. Exact intersection is authoritative."""
    spec = level_spec(level)
    xmin, ymin, xmax, ymax = bounds
    size = spec.resolution_m
    lowcol = max(0, math.floor((xmin - EXTENT_X_MIN) / size) - 1)
    highcol = min(spec.columns - 1, math.floor((xmax - EXTENT_X_MIN) / size))
    lowrow = max(0, math.floor((ymin - EXTENT_Y_MIN) / size) - 1)
    highrow = min(spec.rows - 1, math.floor((ymax - EXTENT_Y_MIN) / size))
    for row in range(lowrow, highrow + 1):
        for col in range(lowcol, highcol + 1):
            yield Cell(level, row, col)


def _row(repository, record_id, role, kind, level, cell, geom_sha, *,
         method, relation, point_state=None, area=None, fraction=None,
         length=None, component=None, segment=None, order=None, edge=None):
    return {
        "Grid_ID": GRID_ID, "Grid_Version": GRID_VERSION,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "Binding_Version": BINDING_VERSION, "Grid_Level": level,
        "Repository": repository, "Record_ID": record_id,
        "Cell_ID": cell.cell_id, "Spatial_Role": role,
        "Source_Geometry_Type": kind, "Binding_Method": method,
        "Uncertainty_Class": "EXACT", "Binding_State": "BOUND",
        "Point_Boundary_State": point_state, "Spatial_Relation": relation,
        "Overlap_Area_m2": area, "Cell_Coverage_Fraction": fraction,
        "Length_In_Cell_m": length, "Component_Index": component,
        "Segment_Index": segment, "Traversal_Order": order,
        "Boundary_Coincident": edge, "Input_Geometry_SHA256": geom_sha,
        "Geometry_State": "VALID_PROJECTED_GEOMETRY",
    }


def _point_rows(repository, record_id, role, level, geom, digest):
    binding = bind_point(geom.x, geom.y, level=level, crs=CRS)
    rows = []
    for identifier in binding.cell_ids:
        # Parse row/column via canonical fixed-width identifier, then validate.
        from spiderweb.geographic_grid_v2 import parse_cell_id
        cell = parse_cell_id(identifier)
        rows.append(_row(repository, record_id, role, "POINT", level, cell, digest,
                         method="COVERS", relation="POINT_COVERED",
                         point_state=binding.state.value))
    return rows


def _polygon_rows(repository, record_id, role, level, geom, digest):
    rows = []
    for cell in _candidate_cells(geom.bounds, level):
        area = geom.intersection(box(*cell.bounds)).area
        if area <= 0:
            continue
        fraction = area / cell.area_m2
        if fraction > 1 and fraction <= 1 + 1e-10:
            raise GridV2Error("GEOS polygon area fraction exceeds one")
        if not 0 < fraction <= 1:
            raise GridV2Error("invalid polygon cell coverage fraction")
        rows.append(_row(repository, record_id, role, "POLYGON", level, cell, digest,
                         method="INTERSECTS_POSITIVE_AREA",
                         relation="POLYGON_POSITIVE_AREA", area=area, fraction=fraction))
    clipped = geom.intersection(GRID_DOMAIN).area
    total = sum(r["Overlap_Area_m2"] for r in rows)
    if not math.isclose(total, clipped, abs_tol=1e-7, rel_tol=1e-9):
        raise GridV2Error("polygon area conservation failure")
    return rows, clipped


def _line_rows(repository, record_id, role, level, geom, digest):
    components = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
    candidate_rows = []
    unique_length = 0.0
    for component_idx, component in enumerate(components):
        coords = list(component.coords)
        for segment_idx in range(len(coords) - 1):
            segment_geom = LineString([coords[segment_idx], coords[segment_idx + 1]])
            if segment_geom.length <= 0:
                raise GridV2Error("zero-length line input segment")
            unique_length += segment_geom.intersection(GRID_DOMAIN).length
            for cell in _candidate_cells(segment_geom.bounds, level):
                clip = segment_geom.intersection(box(*cell.bounds))
                length = clip.length
                if length <= 0:
                    continue
                x0, y0, x1, y1 = cell.bounds
                start, end = coords[segment_idx], coords[segment_idx + 1]
                vertical = start[0] == end[0] and start[0] in (x0, x1)
                horizontal = start[1] == end[1] and start[1] in (y0, y1)
                coincident = vertical or horizontal
                midpoint = clip.interpolate(0.5, normalized=True)
                progress = segment_geom.project(midpoint)
                candidate_rows.append((component_idx, segment_idx, progress, cell.cell_id,
                                       cell, length, coincident))
    candidate_rows.sort(key=lambda x: x[:4])
    rows = [
        _row(repository, record_id, role, "LINE", level, cell, digest,
             method="LINE_POSITIVE_LENGTH", relation="LINE_POSITIVE_LENGTH",
             length=length, component=component_idx, segment=segment_idx,
             order=order, edge=coincident)
        for order, (component_idx, segment_idx, _, _, cell, length, coincident)
        in enumerate(candidate_rows)
    ]
    length_sum = sum(r["Length_In_Cell_m"] for r in rows)
    if length_sum + max(1e-7, unique_length * 1e-9) < unique_length:
        raise GridV2Error("line traversal conservation failure")
    if any(not math.isfinite(r["Length_In_Cell_m"]) for r in rows):
        raise GridV2Error("nonfinite line segment length")
    return rows, unique_length


def bind_exact_geometry(row: Mapping[str, Any], *, level: str) -> GeometryBindingResult:
    level_spec(level)
    repository, record_id, role, kind, geom, digest = _parse_record(row)
    if kind == "POINT":
        rows = _point_rows(repository, record_id, role, level, geom, digest)
        area, unique_length = 0.0, 0.0
    elif kind == "POLYGON":
        rows, area = _polygon_rows(repository, record_id, role, level, geom, digest)
        unique_length = 0.0
    else:
        rows, unique_length = _line_rows(repository, record_id, role, level, geom, digest)
        area = 0.0
    if rows:
        state = "BOUND"
    elif geom.disjoint(GRID_DOMAIN):
        state = "OUTSIDE"
    else:
        state = "TOUCH_ONLY" if kind != "POINT" else "OUTSIDE"
    return GeometryBindingResult(repository, record_id, kind, state, tuple(rows),
                                 unique_length, area)


def bind_exact_geometries(rows: Iterable[Mapping[str, Any]], *, level: str):
    """Reject duplicate record identities across geometry types."""
    level_spec(level)
    results = []
    seen = set()
    for row in rows:
        result = bind_exact_geometry(row, level=level)
        key = (result.repository, result.record_id)
        if key in seen:
            raise GridV2Error(f"duplicate source record identity: {key}")
        seen.add(key)
        results.append(result)
    return tuple(results)


def binding_receipt_vnext(results: Iterable[GeometryBindingResult]):
    items = tuple(results)
    states = {name: sum(r.state == name for r in items)
              for name in ("BOUND", "OUTSIDE", "TOUCH_ONLY")}
    rows = [b for r in items for b in r.bindings]
    lengths = sum(float(b["Length_In_Cell_m"]) for b in rows
                  if b["Source_Geometry_Type"] == "LINE")
    unique = sum(r.unique_clipped_length_m for r in items)
    if sum(states.values()) != len(items) or len(rows) != sum(len(r.bindings) for r in items):
        raise GridV2Error("record/binding count nonconservation")
    return {
        "Contract": BINDING_VERSION, "Certification_State": CONTRACT_STATE,
        "Grid_ID": GRID_ID, "Grid_Version": GRID_VERSION,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "Binding_Schema_SHA256": BINDING_SCHEMA_SHA256,
        "CRS": CRS, "Input_Record_Count": len(items),
        "Binding_Row_Count": len(rows), "State_Counts": states,
        "Cell_Bound_Length_Sum_m": lengths,
        "Unique_Clipped_Traversal_Length_m": unique,
        "Grid_Edge_Length_Multiplicity_m": lengths - unique,
        "Polygon_Clipped_Area_Sum_m2": sum(r.clipped_area_m2 for r in items),
        "Consumer_Activation": "BLOCKED_UNTIL_CERTIFIED",
    }
