"""Freeze the OVNIS PR Grid V2 coordinate-evidence migration blocker."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENOMINATOR = json.loads(
    (
        ROOT
        / "registry/spatial/v2/record_binding_migration_denominator.json"
    ).read_text(encoding="utf-8")
)


def _ovnis_slice() -> tuple[dict, dict]:
    producer = next(
        row
        for row in DENOMINATOR["Producers"]
        if row["Repository"] == "ovnis-pr"
    )
    assert producer["Default_Level"] == "L1"
    assert producer["Cell_Profile_Materializer_State"] == "IMPLEMENTED"
    assert (
        producer["Migration_State"]
        == "BLOCKED_NO_VERIFIED_SOURCE_COORDINATE_DENOMINATOR"
    )
    assert len(producer["Slices"]) == 1
    return producer, producer["Slices"][0]


def test_ovnis_coordinate_evidence_denominator_identity_is_frozen():
    _, row = _ovnis_slice()
    assert row["Slice_ID"] == "OVNIS_MASTER_CASE_COORDINATE_EVIDENCE_AUDIT"
    assert row["Slice_Type"] == "MIGRATION_ELIGIBILITY_AUDIT"
    assert row["Evidence_Commit"] == "2c6fc34970b1cd863821e6fdf6895ea1f454ae99"
    assert row["Source_Commit"] == "6fcbfe58b349c59ed3ebd27ca2bca4afcad4aa22"
    assert row["Source_Path"] == "data/master/master_cases.jsonl"
    assert (
        row["Source_Git_Blob_SHA1"]
        == "428990a32070295f1efe7a7779e4b0e9f7200e82"
    )
    assert (
        row["Coordinate_Evidence_Denominator_Git_Blob_SHA1"]
        == "7622a8d8ba918458a8b98a24a82ea3d7754f8339"
    )
    assert (
        row["Coordinate_Evidence_Auditor_Git_Blob_SHA1"]
        == "9df6cd1a7fbe83567f3469bf82aa78e99eb5eda2"
    )


def test_ovnis_numeric_coordinates_do_not_become_exact_source_points():
    _, row = _ovnis_slice()
    assert row["Migration_Input_Class"] == "EXACT_SOURCE_POINT"
    assert row["Required_Coordinate_Evidence_State"] == "VERIFIED_SOURCE_COORDINATE"
    assert row["Master_Row_Count"] == 470
    assert row["Numeric_Coordinate_Pair_Count"] == 469
    assert row["Missing_Or_NonNumeric_Coordinate_Pair_Count"] == 1
    assert row["Verified_Source_Coordinate_Marker_Count"] == 0
    assert row["Coordinate_Provenance_Field_Row_Count"] == 0
    assert row["Exact_Source_Point_Admissible_Count"] == 0
    assert row["Coordinate_Presence_Is_Exact_Evidence"] is False
    assert row["Location_Confidence_Is_Exact_Evidence"] is False
    assert row["Evidence_Tier_Is_Exact_Coordinate_Evidence"] is False


def test_ovnis_blocked_audit_is_not_migration_execution_or_promotion():
    _, row = _ovnis_slice()
    assert row["Source_Exporter_Geometry_Precision_State"] == "UNKNOWN"
    assert row["Generated_Federation_Exports_Committed"] is False
    assert row["Authority_Execution_State"] == "NOT_EXECUTED"
    assert row["Execution_Evidence_State"] == "AUDIT_PASS_BLOCKED"
    assert row["Geometry_Copied"] is False
    assert row["Promotion_State"] == "CANDIDATE_NOT_CANONICAL"
    assert DENOMINATOR["Unmigrated_Domains_Are_Not_Zero"] is True
