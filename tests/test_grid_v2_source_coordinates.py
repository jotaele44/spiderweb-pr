"""Certification tests for exact source-coordinate PR Grid V2 migration."""

from __future__ import annotations

import pytest

pytest.importorskip("pyproj")

from spiderweb.geographic_grid_v2 import BoundaryState, GridV2Error  # noqa: E402
from spiderweb.grid_v2_source_coordinates import (  # noqa: E402
    BOUNDARY_SNAP_TOLERANCE_M,
    COORDINATE_EVIDENCE_STATE,
    MIGRATION_PROVENANCE_CLASS,
    bind_exact_source_point,
    bind_exact_source_points,
    exact_source_point_from_mapping,
    projection_audit_rows,
    source_binding_receipt,
)


def _row(**overrides):
    row = {
        "Repository": "aguayluz-pr",
        "Record_ID": "gauge-1",
        "Source_X": -66.0,
        "Source_Y": 18.35,
        "Source_CRS": "EPSG:4326",
        "Coordinate_Evidence_State": "VERIFIED_SOURCE_COORDINATE",
        "Uncertainty_Class": "EXACT",
    }
    row.update(overrides)
    return row


def test_wgs84_source_coordinate_projects_and_binds_known_l1_cell():
    record = exact_source_point_from_mapping(_row())
    result = bind_exact_source_point(record, level="L1")

    assert result.binding_result.state is BoundaryState.INTERIOR
    assert [row["Cell_ID"] for row in result.binding_result.bindings] == [
        "PRG2:L1:R077:C0233"
    ]
    assert float(result.projected_x) == pytest.approx(245800.545427, abs=0.01)
    assert float(result.projected_y) == pytest.approx(257239.623334, abs=0.01)
    assert result.pyproj_version is not None
    assert result.proj_version is not None
    assert "+proj=lcc" in result.transform_operation


def test_epsg6566_near_boundary_snaps_before_binding():
    record = exact_source_point_from_mapping(
        _row(
            Record_ID="edge",
            Source_X=247000.0000005,
            Source_Y=255500,
            Source_CRS="EPSG:6566",
        )
    )
    result = bind_exact_source_point(record, level="L1")

    assert result.snap_x is True
    assert result.snap_y is False
    assert result.projected_x == 247000
    assert result.binding_result.state is BoundaryState.EDGE_SHARED
    assert [row["Cell_ID"] for row in result.binding_result.bindings] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]


def test_source_coordinate_requires_explicit_evidence_attestation():
    with pytest.raises(GridV2Error, match="Coordinate_Evidence_State"):
        exact_source_point_from_mapping(
            _row(Coordinate_Evidence_State="APPROXIMATE")
        )


@pytest.mark.parametrize(
    "source_crs",
    ["4326", "WGS84", "+proj=longlat +datum=WGS84", "", None],
)
def test_source_crs_must_be_explicit_epsg_identifier(source_crs):
    with pytest.raises(GridV2Error, match="Source_CRS"):
        exact_source_point_from_mapping(_row(Source_CRS=source_crs))


def test_non_exact_uncertainty_is_rejected():
    with pytest.raises(GridV2Error, match="EXACT"):
        exact_source_point_from_mapping(_row(Uncertainty_Class="APPROXIMATE"))


def test_duplicate_record_identity_fails_closed():
    rows = [
        _row(Record_ID="same"),
        _row(
            Record_ID="same",
            Source_X=-66.01,
            Source_Y=18.36,
        ),
    ]
    with pytest.raises(GridV2Error, match="duplicate"):
        bind_exact_source_points(rows, level="L1")


def test_projection_audit_preserves_lineage_without_changing_binding_rows():
    results = bind_exact_source_points([_row()], level="L1")
    audit = projection_audit_rows(results)

    assert len(audit) == 1
    assert audit[0]["Migration_Provenance_Class"] == MIGRATION_PROVENANCE_CLASS
    assert audit[0]["Coordinate_Evidence_State"] == COORDINATE_EVIDENCE_STATE
    assert audit[0]["Source_CRS"] == "EPSG:4326"
    assert audit[0]["Target_CRS"] == "EPSG:6566"
    assert audit[0]["Source_Record_SHA256"]
    assert audit[0]["Cell_IDs"] == ["PRG2:L1:R077:C0233"]


def test_receipt_preserves_denominators_source_crs_and_snap_policy():
    rows = [
        _row(Record_ID="wgs84"),
        _row(
            Record_ID="edge",
            Source_X=247000.0000005,
            Source_Y=255500,
            Source_CRS="EPSG:6566",
        ),
    ]
    results = bind_exact_source_points(rows, level="L1")
    receipt = source_binding_receipt(results)

    assert receipt["Migration_Provenance_Class"] == MIGRATION_PROVENANCE_CLASS
    assert receipt["Coordinate_Evidence_State"] == COORDINATE_EVIDENCE_STATE
    assert receipt["Input_Record_Count"] == 2
    assert receipt["Projection_Audit_Row_Count"] == 2
    assert receipt["Binding_Row_Count"] == 3
    assert receipt["Boundary_Snap_Record_Count"] == 1
    assert receipt["Boundary_Snap_Tolerance_m"] == str(BOUNDARY_SNAP_TOLERANCE_M)
    assert receipt["Source_CRS_Counts"] == {
        "EPSG:4326": 1,
        "EPSG:6566": 1,
    }
    assert receipt["State_Counts"] == {
        "EDGE_SHARED": 1,
        "INTERIOR": 1,
    }
