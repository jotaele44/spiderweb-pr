"""Canonical authority-side dispatcher for PR Grid V2 record migration.

All record-to-cell membership is computed here, in Spiderweb.  The dispatcher
requires an explicit Migration_Input_Class and never infers a route from field
presence.  This prevents mixed records from silently taking the wrong spatial
path while preserving the frozen pr-grid-v2-binding/1.0 row contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from spiderweb.geographic_grid_v2 import (
    GRID_ID,
    GRID_VERSION,
    GridV2Error,
    level_spec,
)
from spiderweb.grid_v2_bindings import (
    BINDING_SCHEMA_VERSION,
    GRID_MANIFEST_SHA256,
    bind_exact_point,
    exact_point_from_mapping,
)
from spiderweb.grid_v2_geometry_bindings import (
    ADMIN_METHOD,
    DERIVED_METHOD,
    bind_exact_geometry,
    bind_set_geometry,
    exact_geometry_from_mapping,
    set_geometry_from_mapping,
)
from spiderweb.grid_v2_source_coordinates import (
    bind_exact_source_point,
    exact_source_point_from_mapping,
    projection_audit_rows,
)

MIGRATION_CONTRACT = "pr-grid-v2-record-migration/1.0"
MIGRATION_INPUT_CLASSES = (
    "EXACT_PROJECTED_POINT",
    "EXACT_SOURCE_POINT",
    "EXACT_PROJECTED_GEOMETRY",
    "ADMINISTRATIVE_SET",
    "DERIVED_SET",
)
COORDINATE_PROVENANCE = "RECOMPUTED_FROM_SOURCE_COORDINATE"
GEOMETRY_PROVENANCE = "RECOMPUTED_FROM_SOURCE_GEOMETRY"
IDENTITY_DEFAULT = "CANDIDATE_NOT_IDENTITY"


@dataclass(frozen=True)
class MigrationRecordResult:
    repository: str
    record_id: str
    input_class: str
    provenance_class: str
    binding_state: str
    bindings: tuple[dict[str, Any], ...]
    projection_audit: Mapping[str, Any] | None = None


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GridV2Error(f"{name} must be a non-empty string")
    return value.strip()


def _migration_class(row: Mapping[str, Any]) -> str:
    value = _require_text("Migration_Input_Class", row.get("Migration_Input_Class"))
    if value not in MIGRATION_INPUT_CLASSES:
        expected = ", ".join(MIGRATION_INPUT_CLASSES)
        raise GridV2Error(
            f"unsupported Migration_Input_Class {value!r}; expected one of {expected}"
        )
    return value


def _identity(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _require_text("Repository", row.get("Repository")),
        _require_text("Record_ID", row.get("Record_ID")),
    )


def migrate_record(
    row: Mapping[str, Any],
    *,
    level: str,
) -> MigrationRecordResult:
    """Route one explicitly classified record through the authoritative engine."""
    level_spec(level)
    input_class = _migration_class(row)
    repository, record_id = _identity(row)

    if input_class == "EXACT_PROJECTED_POINT":
        result = bind_exact_point(exact_point_from_mapping(row), level=level)
        return MigrationRecordResult(
            repository=repository,
            record_id=record_id,
            input_class=input_class,
            provenance_class=COORDINATE_PROVENANCE,
            binding_state=result.state.value,
            bindings=result.bindings,
        )

    if input_class == "EXACT_SOURCE_POINT":
        result = bind_exact_source_point(
            exact_source_point_from_mapping(row),
            level=level,
        )
        audit = projection_audit_rows((result,))[0]
        return MigrationRecordResult(
            repository=repository,
            record_id=record_id,
            input_class=input_class,
            provenance_class=COORDINATE_PROVENANCE,
            binding_state=result.binding_result.state.value,
            bindings=result.binding_result.bindings,
            projection_audit=audit,
        )

    if input_class == "EXACT_PROJECTED_GEOMETRY":
        result = bind_exact_geometry(exact_geometry_from_mapping(row), level=level)
        return MigrationRecordResult(
            repository=repository,
            record_id=record_id,
            input_class=input_class,
            provenance_class=GEOMETRY_PROVENANCE,
            binding_state="BOUND" if result.bindings else "OUTSIDE_OR_ZERO_MEASURE",
            bindings=result.bindings,
        )

    expected_method = (
        ADMIN_METHOD if input_class == "ADMINISTRATIVE_SET" else DERIVED_METHOD
    )
    if row.get("Binding_Method") != expected_method:
        raise GridV2Error(
            f"{input_class} requires Binding_Method={expected_method}"
        )
    result = bind_set_geometry(set_geometry_from_mapping(row), level=level)
    return MigrationRecordResult(
        repository=repository,
        record_id=record_id,
        input_class=input_class,
        provenance_class=GEOMETRY_PROVENANCE,
        binding_state="SET_BOUND" if result.bindings else "OUTSIDE_OR_ZERO_MEASURE",
        bindings=result.bindings,
    )


def migrate_records(
    rows: Iterable[Mapping[str, Any]],
    *,
    level: str,
) -> tuple[MigrationRecordResult, ...]:
    """Migrate one mixed denominator while rejecting cross-family duplicates."""
    level_spec(level)
    results: list[MigrationRecordResult] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        key = _identity(row)
        if key in seen:
            raise GridV2Error(
                f"duplicate migration record identity: {key[0]}/{key[1]}"
            )
        seen.add(key)
        results.append(migrate_record(row, level=level))

    return tuple(
        sorted(
            results,
            key=lambda value: (
                value.repository,
                value.record_id,
                value.input_class,
            ),
        )
    )


def flatten_binding_rows(
    results: Iterable[MigrationRecordResult],
) -> list[dict[str, Any]]:
    """Return deterministic binding rows without copying canonical geometry."""
    rows = [binding for result in results for binding in result.bindings]
    return sorted(
        rows,
        key=lambda row: (
            str(row["Repository"]),
            str(row["Record_ID"]),
            str(row["Cell_ID"]),
            str(row["Binding_Method"]),
        ),
    )


def migration_audit_rows(
    results: Iterable[MigrationRecordResult],
) -> list[dict[str, Any]]:
    """Emit one lineage row per input record, including projection evidence."""
    rows: list[dict[str, Any]] = []
    for result in results:
        methods = sorted({str(row["Binding_Method"]) for row in result.bindings})
        uncertainties = sorted(
            {str(row["Uncertainty_Class"]) for row in result.bindings}
        )
        rows.append(
            {
                "Repository": result.repository,
                "Record_ID": result.record_id,
                "Migration_Input_Class": result.input_class,
                "Migration_Provenance_Class": result.provenance_class,
                "Binding_State": result.binding_state,
                "Binding_Row_Count": len(result.bindings),
                "Cell_IDs": [str(row["Cell_ID"]) for row in result.bindings],
                "Binding_Methods": methods,
                "Uncertainty_Classes": uncertainties,
                "Projection_Audit": (
                    dict(result.projection_audit)
                    if result.projection_audit is not None
                    else None
                ),
                "Identity_Default": IDENTITY_DEFAULT,
                "Geometry_Copied": False,
            }
        )
    return rows


def migration_receipt(
    results: Iterable[MigrationRecordResult],
) -> dict[str, Any]:
    """Summarize a mixed migration denominator without promoting domain identity."""
    materialized = tuple(results)
    class_counts: dict[str, int] = {}
    provenance_counts: dict[str, int] = {}
    repository_counts: dict[str, int] = {}
    method_row_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    zero_binding_records = 0
    exact_record_count = 0
    non_exact_set_record_count = 0
    projection_rows = 0

    for result in materialized:
        class_counts[result.input_class] = class_counts.get(result.input_class, 0) + 1
        provenance_counts[result.provenance_class] = (
            provenance_counts.get(result.provenance_class, 0) + 1
        )
        repository_counts[result.repository] = (
            repository_counts.get(result.repository, 0) + 1
        )
        state_counts[result.binding_state] = state_counts.get(result.binding_state, 0) + 1
        if not result.bindings:
            zero_binding_records += 1
        if result.projection_audit is not None:
            projection_rows += 1

        uncertainties = {str(row["Uncertainty_Class"]) for row in result.bindings}
        if result.input_class in {
            "EXACT_PROJECTED_POINT",
            "EXACT_SOURCE_POINT",
            "EXACT_PROJECTED_GEOMETRY",
        }:
            exact_record_count += 1
        else:
            non_exact_set_record_count += 1
        if result.bindings and result.input_class.startswith("EXACT_") and uncertainties != {"EXACT"}:
            raise GridV2Error(
                f"exact migration emitted non-exact uncertainty for "
                f"{result.repository}/{result.record_id}"
            )

        for row in result.bindings:
            method = str(row["Binding_Method"])
            method_row_counts[method] = method_row_counts.get(method, 0) + 1

    return {
        "contract": MIGRATION_CONTRACT,
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "Binding_Schema_Version": BINDING_SCHEMA_VERSION,
        "Input_Record_Count": len(materialized),
        "Unique_Record_Identity_Count": len(materialized),
        "Binding_Row_Count": sum(len(result.bindings) for result in materialized),
        "Zero_Binding_Record_Count": zero_binding_records,
        "Projection_Audit_Row_Count": projection_rows,
        "Exact_Record_Count": exact_record_count,
        "Non_Exact_Set_Record_Count": non_exact_set_record_count,
        "Migration_Input_Class_Record_Counts": dict(sorted(class_counts.items())),
        "Migration_Provenance_Class_Record_Counts": dict(
            sorted(provenance_counts.items())
        ),
        "Repository_Record_Counts": dict(sorted(repository_counts.items())),
        "Binding_Method_Row_Counts": dict(sorted(method_row_counts.items())),
        "Binding_State_Record_Counts": dict(sorted(state_counts.items())),
        "Identity_Default": IDENTITY_DEFAULT,
        "Geometry_Copied": False,
    }
