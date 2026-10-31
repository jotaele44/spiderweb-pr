"""Authority-side exact source-coordinate migration into PR Grid V2.

This layer preserves the existing pr-grid-v2-binding/1.0 row contract.
It transforms evidence-backed exact source coordinates into EPSG:6566 inside
Spiderweb, binds them with the existing exact-point authority, and emits a
separate projection-audit artifact. Consumers must never perform this transform.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Iterable, Mapping

from spiderweb.geographic_grid_v2 import (
    CRS,
    GRID_ID,
    GRID_VERSION,
    GridV2Error,
    ORIGIN_X,
    ORIGIN_Y,
    level_spec,
)
from spiderweb.grid_v2_bindings import (
    BINDING_SCHEMA_VERSION,
    GRID_MANIFEST_SHA256,
    BindingResult,
    ExactPointRecord,
    bind_exact_point,
)

MIGRATION_PROVENANCE_CLASS = "RECOMPUTED_FROM_SOURCE_COORDINATE"
COORDINATE_EVIDENCE_STATE = "VERIFIED_SOURCE_COORDINATE"
BINDING_SCHEMA_SHA256 = "dabc461e47134b3b150be9aeb23b3d0097563493b33b3187538255e06b16a022"
BOUNDARY_SNAP_TOLERANCE_M = Decimal("0.000001")
_EPSG_RE = re.compile(r"^EPSG:([1-9][0-9]*)$")


@dataclass(frozen=True)
class ExactSourcePointRecord:
    repository: str
    record_id: str
    source_x: Any
    source_y: Any
    source_crs: str
    coordinate_evidence_state: str
    spatial_role: str = "POINT_LOCATION"
    uncertainty_class: str = "EXACT"
    source_record_sha256: str | None = None


@dataclass(frozen=True)
class SourcePointBindingResult:
    record: ExactSourcePointRecord
    binding_result: BindingResult
    projected_x: Decimal
    projected_y: Decimal
    snap_x: bool
    snap_y: bool
    transform_operation: str
    pyproj_version: str | None
    proj_version: str | None


def _canonical_sha(row: Mapping[str, Any]) -> str:
    payload = (
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GridV2Error(f"{name} must be a non-empty string")
    return value.strip()


def _require_epsg(value: object) -> str:
    text = _require_text("Source_CRS", value).upper()
    match = _EPSG_RE.fullmatch(text)
    if match is None:
        raise GridV2Error("Source_CRS must be an explicit EPSG:<code> identifier")
    return f"EPSG:{int(match.group(1))}"


def exact_source_point_from_mapping(row: Mapping[str, Any]) -> ExactSourcePointRecord:
    repository = _require_text("Repository", row.get("Repository"))
    record_id = _require_text("Record_ID", row.get("Record_ID"))
    spatial_role = _require_text(
        "Spatial_Role", row.get("Spatial_Role", "POINT_LOCATION")
    )
    uncertainty = row.get("Uncertainty_Class", "EXACT")
    if uncertainty != "EXACT":
        raise GridV2Error(
            "source-coordinate V2 migration only accepts Uncertainty_Class='EXACT'"
        )
    evidence = row.get("Coordinate_Evidence_State")
    if evidence != COORDINATE_EVIDENCE_STATE:
        raise GridV2Error(
            "Coordinate_Evidence_State must be 'VERIFIED_SOURCE_COORDINATE'"
        )
    if "Source_X" not in row or "Source_Y" not in row:
        raise GridV2Error("source-coordinate input requires Source_X and Source_Y")
    return ExactSourcePointRecord(
        repository=repository,
        record_id=record_id,
        source_x=row["Source_X"],
        source_y=row["Source_Y"],
        source_crs=_require_epsg(row.get("Source_CRS")),
        coordinate_evidence_state=evidence,
        spatial_role=spatial_role,
        uncertainty_class=uncertainty,
        source_record_sha256=_canonical_sha(row),
    )


def _as_finite_float(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GridV2Error(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise GridV2Error(f"{name} must be finite")
    return number


def _transform_xy(
    x: Any,
    y: Any,
    *,
    source_crs: str,
) -> tuple[Decimal, Decimal, str, str | None, str | None]:
    sx = _as_finite_float("Source_X", x)
    sy = _as_finite_float("Source_Y", y)
    if source_crs == CRS:
        return (
            Decimal(str(sx)),
            Decimal(str(sy)),
            "IDENTITY_EPSG_6566",
            None,
            None,
        )

    try:
        import pyproj
        from pyproj import Transformer
        from pyproj.exceptions import ProjError
    except ImportError as exc:
        raise GridV2Error(
            "pyproj is required for non-EPSG:6566 source-coordinate migration"
        ) from exc

    try:
        transformer = Transformer.from_crs(
            source_crs,
            CRS,
            always_xy=True,
            allow_ballpark=False,
            only_best=True,
        )
        tx, ty = transformer.transform(sx, sy, errcheck=True)
        if not math.isfinite(tx) or not math.isfinite(ty):
            raise GridV2Error("source CRS transform produced non-finite coordinates")
        operation = transformer.get_last_used_operation()
        operation_text = (
            operation.to_proj4() if operation is not None else transformer.description
        )
    except (ProjError, ValueError, TypeError) as exc:
        raise GridV2Error(
            f"source CRS transform failed from {source_crs} to {CRS}: {exc}"
        ) from exc

    return (
        Decimal(str(tx)),
        Decimal(str(ty)),
        str(operation_text),
        str(pyproj.__version__),
        str(pyproj.proj_version_str),
    )


def _snap_axis(
    value: Decimal,
    *,
    origin: int,
    resolution_m: int,
) -> tuple[Decimal, bool]:
    step = Decimal(resolution_m)
    anchor = Decimal(origin)
    index = ((value - anchor) / step).to_integral_value(rounding=ROUND_HALF_EVEN)
    boundary = anchor + index * step
    if abs(value - boundary) <= BOUNDARY_SNAP_TOLERANCE_M:
        return boundary, True
    return value, False


def bind_exact_source_point(
    record: ExactSourcePointRecord,
    *,
    level: str,
) -> SourcePointBindingResult:
    spec = level_spec(level)
    if record.coordinate_evidence_state != COORDINATE_EVIDENCE_STATE:
        raise GridV2Error(
            "source-coordinate binding requires VERIFIED_SOURCE_COORDINATE evidence"
        )
    if record.uncertainty_class != "EXACT":
        raise GridV2Error(
            "source-coordinate V2 migration only accepts Uncertainty_Class='EXACT'"
        )

    projected_x, projected_y, operation, pyproj_version, proj_version = _transform_xy(
        record.source_x,
        record.source_y,
        source_crs=_require_epsg(record.source_crs),
    )
    projected_x, snap_x = _snap_axis(
        projected_x,
        origin=ORIGIN_X,
        resolution_m=spec.resolution_m,
    )
    projected_y, snap_y = _snap_axis(
        projected_y,
        origin=ORIGIN_Y,
        resolution_m=spec.resolution_m,
    )

    binding = bind_exact_point(
        ExactPointRecord(
            repository=record.repository,
            record_id=record.record_id,
            x=projected_x,
            y=projected_y,
            crs=CRS,
            spatial_role=record.spatial_role,
            uncertainty_class=record.uncertainty_class,
        ),
        level=level,
    )
    return SourcePointBindingResult(
        record=record,
        binding_result=binding,
        projected_x=projected_x,
        projected_y=projected_y,
        snap_x=snap_x,
        snap_y=snap_y,
        transform_operation=operation,
        pyproj_version=pyproj_version,
        proj_version=proj_version,
    )


def bind_exact_source_points(
    rows: Iterable[Mapping[str, Any]],
    *,
    level: str,
) -> tuple[SourcePointBindingResult, ...]:
    level_spec(level)
    results: list[SourcePointBindingResult] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        record = exact_source_point_from_mapping(row)
        key = (record.repository, record.record_id)
        if key in seen:
            raise GridV2Error(
                f"duplicate exact source-coordinate record identity: "
                f"{record.repository}/{record.record_id}"
            )
        seen.add(key)
        results.append(bind_exact_source_point(record, level=level))
    return tuple(results)


def flatten_source_binding_rows(
    results: Iterable[SourcePointBindingResult],
) -> list[dict[str, Any]]:
    return [
        row
        for result in results
        for row in result.binding_result.bindings
    ]


def projection_audit_rows(
    results: Iterable[SourcePointBindingResult],
) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        record = result.record
        rows.append(
            {
                "Repository": record.repository,
                "Record_ID": record.record_id,
                "Migration_Provenance_Class": MIGRATION_PROVENANCE_CLASS,
                "Coordinate_Evidence_State": record.coordinate_evidence_state,
                "Source_Record_SHA256": record.source_record_sha256,
                "Source_CRS": record.source_crs,
                "Target_CRS": CRS,
                "Source_X": record.source_x,
                "Source_Y": record.source_y,
                "Projected_X": str(result.projected_x),
                "Projected_Y": str(result.projected_y),
                "Boundary_Snap_X": result.snap_x,
                "Boundary_Snap_Y": result.snap_y,
                "Boundary_Snap_Tolerance_m": str(BOUNDARY_SNAP_TOLERANCE_M),
                "Transform_Operation": result.transform_operation,
                "PyProj_Version": result.pyproj_version,
                "PROJ_Version": result.proj_version,
                "Grid_Level": result.binding_result.level,
                "Binding_State": result.binding_result.state.value,
                "Cell_IDs": [
                    row["Cell_ID"] for row in result.binding_result.bindings
                ],
            }
        )
    return rows


def source_binding_receipt(
    results: Iterable[SourcePointBindingResult],
) -> dict[str, Any]:
    materialized = tuple(results)
    state_counts: dict[str, int] = {}
    source_crs_counts: dict[str, int] = {}
    binding_rows = 0
    snap_record_count = 0
    for result in materialized:
        state = result.binding_result.state.value
        state_counts[state] = state_counts.get(state, 0) + 1
        source_crs = result.record.source_crs
        source_crs_counts[source_crs] = source_crs_counts.get(source_crs, 0) + 1
        binding_rows += len(result.binding_result.bindings)
        if result.snap_x or result.snap_y:
            snap_record_count += 1

    return {
        "contract": "pr-grid-v2-source-coordinate-binding-receipt/1.0",
        "Migration_Provenance_Class": MIGRATION_PROVENANCE_CLASS,
        "Coordinate_Evidence_State": COORDINATE_EVIDENCE_STATE,
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "Binding_Schema_Version": BINDING_SCHEMA_VERSION,
        "Binding_Schema_SHA256": BINDING_SCHEMA_SHA256,
        "Target_CRS": CRS,
        "Boundary_Snap_Tolerance_m": str(BOUNDARY_SNAP_TOLERANCE_M),
        "Input_Record_Count": len(materialized),
        "Binding_Row_Count": binding_rows,
        "Projection_Audit_Row_Count": len(materialized),
        "Boundary_Snap_Record_Count": snap_record_count,
        "State_Counts": dict(sorted(state_counts.items())),
        "Source_CRS_Counts": dict(sorted(source_crs_counts.items())),
    }
