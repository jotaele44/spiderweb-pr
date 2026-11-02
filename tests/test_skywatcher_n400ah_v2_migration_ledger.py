"""Freeze the Skywatcher N400AH Grid V2 migration evidence boundary."""

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


def _slice() -> dict:
    producer = next(
        row for row in DENOMINATOR["Producers"]
        if row["Repository"] == "skywatcher-pr"
    )
    assert (
        producer["Migration_State"]
        == "SOURCE_QUALIFIED_LOCAL_RECOMPUTATION_PASS_CI_BLOCKED_RIGHTS"
    )
    assert len(producer["Slices"]) == 1
    return producer["Slices"][0]


def test_n400ah_source_identity_and_exact_coordinate_denominator_are_frozen():
    row = _slice()
    assert row["Slice_ID"] == "N400AH_STRUCTURED_TRACKS_2026Q2_Q3_v1"
    assert row["Evidence_Commit"] == "7f5a3be1fed169d2521cb8c728101246ffb17b6c"
    assert (
        row["Source_Hash_Ledger_Git_Blob_SHA1"]
        == "cd3a7afe618f3fe29546336aa03dedbdbab679f8"
    )
    assert (
        row["Source_Recovery_Attestation_Git_Blob_SHA1"]
        == "d36ef10ef3a706f2dba252f8f9ada38f67fa16d6"
    )
    assert row["Frozen_Provider_Member_Count"] == 50
    assert row["Frozen_Provider_Matched_Byte_Identical_Count"] == 50
    assert row["Coordinate_Evidence_State"] == "VERIFIED_SOURCE_COORDINATE"
    assert row["Migration_Input_Class"] == "EXACT_SOURCE_POINT"
    assert row["Source_CRS"] == "EPSG:4326"
    assert row["Target_Level"] == "L2"


def test_n400ah_local_recomputation_arithmetic_closes_without_promotion():
    row = _slice()
    assert row["Input_Record_Count"] == 12455
    assert row["Interior_Record_Count"] == 10875
    assert row["Outside_Record_Count"] == 1580
    assert row["Interior_Record_Count"] + row["Outside_Record_Count"] == 12455
    assert row["Binding_Row_Count"] == 10875
    assert row["Edge_Shared_Record_Count"] == 0
    assert row["Corner_Shared_Record_Count"] == 0
    assert row["Boundary_Snap_Record_Count"] == 0
    assert row["Unique_Bound_L2_Cell_Count"] == 3211
    assert (
        row["Local_Recomputation_Receipt_SHA256"]
        == "e3a49f4d35e269483cfeacfaca0d6fcb515353a3fc99c6023a1fdc3a675596b7"
    )
    assert (
        row["Execution_Evidence_State"]
        == "INDEPENDENT_NUMERIC_RECOMPUTATION_PASS"
    )
    assert row["Authority_Execution_State"] == "NOT_EXECUTED"
    assert row["Promotion_State"] == "CANDIDATE_NOT_CANONICAL"
    assert row["Geometry_Copied"] is False


def test_n400ah_rights_gate_forbids_public_source_or_derived_track_material():
    row = _slice()
    assert (
        row["CI_Reproducibility_State"]
        == "BLOCKED_REDISTRIBUTION_RIGHTS_UNVERIFIED"
    )
    assert row["Provider_Source_Redistribution_State"] == "UNVERIFIED"
    assert row["Original_Source_Archive_Byte_Identity_State"] == "UNRESOLVED"
    assert row["Recovery_Container_Comparison_State"] == "DISTINCT_PAYLOADS"
    assert row["Raw_Provider_Payloads_Committed"] is False
    assert row["Derived_Coordinate_Rows_Committed"] is False
    assert row["Per_Cell_Aggregate_Committed"] is False
    assert row["Profile_Execution_State"] == "NOT_EXECUTED"
