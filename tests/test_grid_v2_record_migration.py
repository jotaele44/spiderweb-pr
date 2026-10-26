"""Certification tests for the canonical PR Grid V2 record migration dispatcher."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from spiderweb.geographic_grid_v2 import GridV2Error
from spiderweb.grid_v2_record_migration import (
    COORDINATE_PROVENANCE,
    GEOMETRY_PROVENANCE,
    flatten_binding_rows,
    migrate_records,
    migration_audit_rows,
    migration_receipt,
)


def _mixed_rows() -> list[dict[str, object]]:
    return [
        {
            "Migration_Input_Class": "EXACT_PROJECTED_POINT",
            "Repository": "aguayluz-pr",
            "Record_ID": "projected-point",
            "X": 246500,
            "Y": 255500,
            "CRS": "EPSG:6566",
            "Spatial_Role": "GAUGE",
            "Uncertainty_Class": "EXACT",
        },
        {
            "Migration_Input_Class": "EXACT_SOURCE_POINT",
            "Repository": "ovnis-pr",
            "Record_ID": "source-edge",
            "Source_X": 247000,
            "Source_Y": 255500,
            "Source_CRS": "EPSG:6566",
            "Coordinate_Evidence_State": "VERIFIED_SOURCE_COORDINATE",
            "Spatial_Role": "REPORTED_LOCATION",
            "Uncertainty_Class": "EXACT",
        },
        {
            "Migration_Input_Class": "EXACT_PROJECTED_GEOMETRY",
            "Repository": "skywatcher-pr",
            "Record_ID": "track",
            "CRS": "EPSG:6566",
            "Spatial_Role": "TRACK_SEGMENT",
            "Uncertainty_Class": "EXACT",
            "Geometry": {
                "type": "LineString",
                "coordinates": [[246100, 255500], [247900, 255500]],
            },
        },
        {
            "Migration_Input_Class": "ADMINISTRATIVE_SET",
            "Repository": "ovnis-pr",
            "Record_ID": "municipality-only",
            "CRS": "EPSG:6566",
            "Binding_Method": "ADMINISTRATIVE_SET",
            "Uncertainty_Class": "ADMINISTRATIVE_ONLY",
            "Geometry_Evidence_State": "VERIFIED_ADMINISTRATIVE_GEOMETRY",
            "Spatial_Role": "REPORTED_MUNICIPALITY_EXTENT",
            "Geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [246500, 255250],
                    [247500, 255250],
                    [247500, 255750],
                    [246500, 255750],
                    [246500, 255250],
                ]],
            },
        },
        {
            "Migration_Input_Class": "DERIVED_SET",
            "Repository": "moneysweep-pr",
            "Record_ID": "derived-area",
            "CRS": "EPSG:6566",
            "Binding_Method": "DERIVED_SET",
            "Uncertainty_Class": "DERIVED",
            "Geometry_Evidence_State": "VERIFIED_DERIVED_GEOMETRY",
            "Spatial_Role": "DERIVED_ANALYSIS_EXTENT",
            "Geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [246500, 255250],
                    [247500, 255250],
                    [247500, 255750],
                    [246500, 255750],
                    [246500, 255250],
                ]],
            },
        },
    ]


def test_mixed_dispatch_preserves_all_families_and_boundary_multiplicity():
    results = migrate_records(_mixed_rows(), level="L1")
    rows = flatten_binding_rows(results)
    receipt = migration_receipt(results)

    assert len(results) == 5
    assert len(rows) == 9
    assert receipt["Input_Record_Count"] == 5
    assert receipt["Unique_Record_Identity_Count"] == 5
    assert receipt["Binding_Row_Count"] == 9
    assert receipt["Zero_Binding_Record_Count"] == 0
    assert receipt["Projection_Audit_Row_Count"] == 1
    assert receipt["Exact_Record_Count"] == 3
    assert receipt["Non_Exact_Set_Record_Count"] == 2
    assert receipt["Migration_Input_Class_Record_Counts"] == {
        "ADMINISTRATIVE_SET": 1,
        "DERIVED_SET": 1,
        "EXACT_PROJECTED_GEOMETRY": 1,
        "EXACT_PROJECTED_POINT": 1,
        "EXACT_SOURCE_POINT": 1,
    }
    assert receipt["Migration_Provenance_Class_Record_Counts"] == {
        COORDINATE_PROVENANCE: 2,
        GEOMETRY_PROVENANCE: 3,
    }
    assert receipt["Binding_Method_Row_Counts"] == {
        "ADMINISTRATIVE_SET": 2,
        "COVERS": 3,
        "DERIVED_SET": 2,
        "LINE_POSITIVE_LENGTH": 2,
    }
    assert receipt["Geometry_Copied"] is False
    assert receipt["Identity_Default"] == "CANDIDATE_NOT_IDENTITY"

    edge_rows = [
        row for row in rows
        if row["Repository"] == "ovnis-pr" and row["Record_ID"] == "source-edge"
    ]
    assert [row["Cell_ID"] for row in edge_rows] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]


def test_audit_preserves_projection_lineage_and_never_copies_geometry():
    results = migrate_records(_mixed_rows(), level="L1")
    audit = migration_audit_rows(results)
    source = next(row for row in audit if row["Record_ID"] == "source-edge")
    admin = next(row for row in audit if row["Record_ID"] == "municipality-only")

    assert source["Migration_Provenance_Class"] == COORDINATE_PROVENANCE
    assert source["Projection_Audit"]["Source_CRS"] == "EPSG:6566"
    assert source["Projection_Audit"]["Target_CRS"] == "EPSG:6566"
    assert source["Projection_Audit"]["Transform_Operation"] == "IDENTITY_EPSG_6566"
    assert source["Geometry_Copied"] is False
    assert admin["Migration_Provenance_Class"] == GEOMETRY_PROVENANCE
    assert admin["Uncertainty_Classes"] == ["ADMINISTRATIVE_ONLY"]
    assert admin["Geometry_Copied"] is False


def test_migration_input_class_is_mandatory_and_never_inferred():
    row = _mixed_rows()[0].copy()
    row.pop("Migration_Input_Class")
    with pytest.raises(GridV2Error, match="Migration_Input_Class"):
        migrate_records([row], level="L1")


def test_unknown_migration_class_fails_closed():
    row = _mixed_rows()[0].copy()
    row["Migration_Input_Class"] = "AUTO_DETECT"
    with pytest.raises(GridV2Error, match="unsupported Migration_Input_Class"):
        migrate_records([row], level="L1")


def test_set_class_and_binding_method_must_agree():
    row = _mixed_rows()[3].copy()
    row["Binding_Method"] = "DERIVED_SET"
    with pytest.raises(GridV2Error, match="ADMINISTRATIVE_SET requires"):
        migrate_records([row], level="L1")


def test_duplicate_identity_across_different_families_fails_before_routing():
    first = _mixed_rows()[0]
    second = {
        "Migration_Input_Class": "EXACT_PROJECTED_GEOMETRY",
        "Repository": first["Repository"],
        "Record_ID": first["Record_ID"],
    }
    with pytest.raises(GridV2Error, match="duplicate migration record identity"):
        migrate_records([first, second], level="L1")


def test_wrong_level_fails_closed():
    with pytest.raises(GridV2Error, match="unknown grid level"):
        migrate_records(_mixed_rows(), level="L9")


def test_nwps_durable_certification_closes_denominator_without_promotion():
    root = Path(__file__).resolve().parents[1]
    receipt_path = root / "registry/spatial/v2/aguayluz_nwps_l1_migration.certification.json"
    denominator_path = root / "registry/spatial/v2/record_binding_migration_denominator.json"
    request_path = root / "registry/spatial/v2/aguayluz_nwps_l1_migration.request.json"

    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    denominator = json.loads(denominator_path.read_text())
    request = json.loads(request_path.read_text())

    producer = next(
        row for row in denominator["Producers"]
        if row["Repository"] == "aguayluz-pr"
    )
    slice_row = next(
        row for row in producer["Slices"]
        if row["Slice_ID"] == "NWPS_GAUGE_STATE"
    )

    assert denominator["Geometry_Authority_Commit"] == "b8f5cf303ab7fc2b6ed006edce0fb12e1344a096"
    assert producer["Migration_State"] == "FIRST_SLICE_EXECUTION_CERTIFIED_CANDIDATE"
    assert slice_row["Execution_Evidence_State"] == "FROZEN_CERTIFICATION_RECEIPT_PASS"
    assert slice_row["Promotion_State"] == "CANDIDATE_NOT_CANONICAL"
    assert slice_row["Certification_Receipt"] == str(
        receipt_path.relative_to(root)
    )
    assert slice_row["Certification_Receipt_SHA256"] == hashlib.sha256(
        receipt_bytes
    ).hexdigest()

    assert receipt["State"] == "PASS"
    assert receipt["Promotion_State"] == "CANDIDATE_NOT_CANONICAL"
    assert receipt["Geometry_Copied"] is False
    assert receipt["Input_Record_Count"] == 118
    assert receipt["Binding_Row_Count"] == 118
    assert receipt["Binding_State_Counts"] == {"INTERIOR": 118}
    assert receipt["Profile_Count"] == 111
    assert receipt["Profile_Data_State_Counts"] == {"HAS_RECORDS": 111}
    assert receipt["Migration_Provenance_Class"] == "RECOMPUTED_FROM_SOURCE_COORDINATE"
    assert receipt["Profile_Migration_Class"] == "SPIDERWEB_CERTIFIED_EXACT_BINDINGS"

    assert request["state"] == "EXECUTION_CERTIFIED_CANDIDATE_NOT_CANONICAL"
    assert request["certification_receipt"] == str(
        receipt_path.relative_to(root)
    )
    assert request["certification_receipt_sha256"] == hashlib.sha256(
        receipt_bytes
    ).hexdigest()
