"""Authoritative record-to-cell binding materialization for PR grid V2.

Initial migration slice: exact point observations already expressed in the
canonical projected CRS (EPSG:6566). Spiderweb performs the binding. Consumers
must not recompute spatial membership.

Boundary semantics are preserved:
- INTERIOR -> one binding row
- EDGE_SHARED -> two binding rows
- CORNER_SHARED -> four binding rows
- OUTSIDE -> no binding rows, explicit OUTSIDE receipt
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from spiderweb.geographic_grid_v2 import (
    CRS,
    GRID_ID,
    GRID_VERSION,
    BoundaryState,
    GridV2Error,
    bind_point,
    level_spec,
)

BINDING_SCHEMA_VERSION = "pr-grid-v2-binding/1.0"
BINDING_METHOD = "COVERS"
UNCERTAINTY_CLASS = "EXACT"
GEOMETRY_STATE = "VERIFIED_PROJECTED_POINT"


@dataclass(frozen=True)
class ExactPointRecord:
    repository: str
    record_id: str
    x: Any
    y: Any
    crs: str
    spatial_role: str = "POINT_LOCATION"
    uncertainty_class: str = UNCERTAINTY_CLASS


@dataclass(frozen=True)
class BindingResult:
    repository: str
    record_id: str
    level: str
    state: BoundaryState
    bindings: tuple[dict[str, Any], ...]


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GridV2Error(f"{name} must be a non-empty string")
    return value.strip()


def exact_point_from_mapping(row: Mapping[str, Any]) -> ExactPointRecord:
    """Parse one strict exact-point input record."""
    repository = _require_text("Repository", row.get("Repository"))
    record_id = _require_text("Record_ID", row.get("Record_ID"))
    spatial_role = _require_text("Spatial_Role", row.get("Spatial_Role", "POINT_LOCATION"))

    uncertainty = row.get("Uncertainty_Class", UNCERTAINTY_CLASS)
    if uncertainty != UNCERTAINTY_CLASS:
        raise GridV2Error(
            "exact-point V2 migration only accepts Uncertainty_Class='EXACT'"
        )

    crs = row.get("CRS")
    if not isinstance(crs, str) or not crs.strip():
        raise GridV2Error("missing CRS")

    if "X" not in row or "Y" not in row:
        raise GridV2Error("exact-point input requires X and Y")

    return ExactPointRecord(
        repository=repository,
        record_id=record_id,
        x=row["X"],
        y=row["Y"],
        crs=crs,
        spatial_role=spatial_role,
        uncertainty_class=uncertainty,
    )


def bind_exact_point(record: ExactPointRecord, *, level: str) -> BindingResult:
    """Bind one exact projected point to the canonical V2 hierarchy."""
    level_spec(level)
    repository = _require_text("Repository", record.repository)
    record_id = _require_text("Record_ID", record.record_id)
    spatial_role = _require_text("Spatial_Role", record.spatial_role)

    if record.uncertainty_class != UNCERTAINTY_CLASS:
        raise GridV2Error(
            "exact-point V2 migration only accepts Uncertainty_Class='EXACT'"
        )

    point = bind_point(
        record.x,
        record.y,
        level=level,
        crs=record.crs,
    )

    rows = tuple(
        {
            "Grid_ID": GRID_ID,
            "Grid_Version": GRID_VERSION,
            "Grid_Level": level,
            "Repository": repository,
            "Record_ID": record_id,
            "Cell_ID": cell_id,
            "Spatial_Role": spatial_role,
            "Binding_Method": BINDING_METHOD,
            "Uncertainty_Class": UNCERTAINTY_CLASS,
            "Binding_State": point.state.value,
            "Overlap_Area_m2": None,
            "Cell_Coverage_Fraction": None,
            "Length_In_Cell_m": None,
            "Binding_Version": BINDING_SCHEMA_VERSION,
            "Geometry_State": GEOMETRY_STATE,
            "Confidence": 1.0,
        }
        for cell_id in point.cell_ids
    )

    return BindingResult(
        repository=repository,
        record_id=record_id,
        level=level,
        state=point.state,
        bindings=rows,
    )


def bind_exact_points(
    rows: Iterable[Mapping[str, Any]],
    *,
    level: str,
) -> tuple[BindingResult, ...]:
    """Bind a denominator of exact points and reject duplicate record identities."""
    level_spec(level)
    results: list[BindingResult] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        record = exact_point_from_mapping(row)
        key = (record.repository, record.record_id)
        if key in seen:
            raise GridV2Error(
                f"duplicate exact-point record identity: {record.repository}/{record.record_id}"
            )
        seen.add(key)
        results.append(bind_exact_point(record, level=level))

    return tuple(results)


def flatten_binding_rows(results: Iterable[BindingResult]) -> list[dict[str, Any]]:
    """Flatten only realized cell bindings; OUTSIDE remains visible in results."""
    return [binding for result in results for binding in result.bindings]


def binding_receipt(results: Iterable[BindingResult]) -> dict[str, Any]:
    """Summarize migration outcomes without collapsing boundary multiplicity."""
    materialized = tuple(results)
    state_counts: dict[str, int] = {}
    binding_rows = 0
    for result in materialized:
        state_counts[result.state.value] = state_counts.get(result.state.value, 0) + 1
        binding_rows += len(result.bindings)

    return {
        "contract": "pr-grid-v2-exact-point-binding-receipt/1.0",
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "CRS": CRS,
        "Binding_Schema_Version": BINDING_SCHEMA_VERSION,
        "Input_Record_Count": len(materialized),
        "Binding_Row_Count": binding_rows,
        "State_Counts": dict(sorted(state_counts.items())),
    }
