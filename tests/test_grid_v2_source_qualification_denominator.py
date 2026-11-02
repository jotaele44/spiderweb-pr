"""Migration denominator regression for the second evidence-qualified source slice."""

from __future__ import annotations

import json
from pathlib import Path

DENOMINATOR = (
    Path(__file__).resolve().parents[1]
    / "registry/spatial/v2/record_binding_migration_denominator.json"
)


def _rows() -> tuple[dict, dict]:
    value = json.loads(DENOMINATOR.read_text(encoding="utf-8"))
    producer = next(
        row for row in value["Producers"]
        if row["Repository"] == "skywatcher-pr"
    )
    assert len(producer["Slices"]) == 1
    return value, producer


def test_second_source_slice_is_qualified_but_not_executed():
    _, producer = _rows()
    row = producer["Slices"][0]
    assert producer["Migration_State"] == "SOURCE_QUALIFIED_EXECUTION_BLOCKED"
    assert row["Expected_Record_Count"] == 12455
    assert row["Source_File_Count"] == 50
    assert row["Coordinate_Evidence_State"] == "VERIFIED_SOURCE_COORDINATE"
    assert row["Migration_Input_Class"] == "EXACT_SOURCE_POINT"
    assert row["Target_Level"] == "L2"
    assert row["Execution_Evidence_State"] == "BLOCKED_SOURCE_NOT_CI_ADDRESSABLE"
    assert row["Promotion_State"] == "CANDIDATE_NOT_CANONICAL"
    assert "Binding_Row_Count" not in row
    assert "Profile_Count" not in row
    assert "Workflow_Artifact_SHA256" not in row


def test_container_identity_is_separate_from_member_payload_identity():
    _, producer = _rows()
    row = producer["Slices"][0]
    assert row["Original_Archive_Byte_Identity"] == "UNRESOLVED"
    assert row["Recovery_Container_Comparison_State"] == "DISTINCT_PAYLOADS"
    assert row["In_Scope_Source_Payload_State"] == "PASS_BYTE_IDENTICAL_SUBSET"


def test_remaining_unmigrated_domains_are_not_zero_record_claims():
    denominator, _ = _rows()
    assert denominator["Unmigrated_Domains_Are_Not_Zero"] is True
    states = {
        row["Repository"]: row["Migration_State"]
        for row in denominator["Producers"]
    }
    assert states["aguayluz-pr"] == "FIRST_SLICE_EXECUTION_FROZEN"
    assert states["skywatcher-pr"] == "SOURCE_QUALIFIED_EXECUTION_BLOCKED"
    assert states["ovnis-pr"] == "NOT_YET_MIGRATED"
    assert states["moneysweep-pr"] == "NOT_YET_MIGRATED"
    assert states["centinelas-pr"] == "NOT_YET_MIGRATED"
