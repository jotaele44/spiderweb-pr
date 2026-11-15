"""Certification tests for administrative and derived PR grid V2 set bindings."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from spiderweb.geographic_grid_v2 import GridV2Error
from spiderweb.grid_v2_geometry_bindings import (
    ADMIN_EVIDENCE_STATE,
    ADMIN_METHOD,
    ADMIN_UNCERTAINTY,
    DERIVED_EVIDENCE_STATE,
    DERIVED_METHOD,
    DERIVED_UNCERTAINTY,
    SetGeometryRecord,
    bind_set_geometries,
    bind_set_geometry,
    flatten_set_binding_rows,
    set_binding_receipt,
    set_geometry_from_mapping,
)


def _polygon() -> Polygon:
    return Polygon(
        [(246500, 255250), (247500, 255250), (247500, 255750), (246500, 255750)]
    )


def test_administrative_set_preserves_non_exact_epistemic_state():
    result = bind_set_geometry(
        SetGeometryRecord(
            "ovnis-pr",
            "municipality-only",
            _polygon(),
            "EPSG:6566",
            "REPORTED_MUNICIPALITY_EXTENT",
            ADMIN_METHOD,
            ADMIN_UNCERTAINTY,
            ADMIN_EVIDENCE_STATE,
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]
    assert all(row["Binding_Method"] == ADMIN_METHOD for row in result.bindings)
    assert all(row["Uncertainty_Class"] == ADMIN_UNCERTAINTY for row in result.bindings)
    assert all(row["Geometry_State"] == ADMIN_EVIDENCE_STATE for row in result.bindings)
    assert all(row["Confidence"] is None for row in result.bindings)
    assert sum(row["Overlap_Area_m2"] for row in result.bindings) == pytest.approx(500000.0)


def test_derived_set_preserves_derived_state():
    result = bind_set_geometry(
        SetGeometryRecord(
            "moneysweep-pr",
            "derived-corridor",
            _polygon(),
            "EPSG:6566",
            "DERIVED_ANALYSIS_EXTENT",
            DERIVED_METHOD,
            DERIVED_UNCERTAINTY,
            DERIVED_EVIDENCE_STATE,
        ),
        level="L1",
    )
    assert len(result.bindings) == 2
    assert all(row["Binding_Method"] == DERIVED_METHOD for row in result.bindings)
    assert all(row["Uncertainty_Class"] == DERIVED_UNCERTAINTY for row in result.bindings)
    assert all(row["Geometry_State"] == DERIVED_EVIDENCE_STATE for row in result.bindings)


def test_touch_only_cells_do_not_enter_set_membership():
    polygon = Polygon(
        [(247000, 255100), (247500, 255100), (247500, 255900), (247000, 255900)]
    )
    result = bind_set_geometry(
        SetGeometryRecord(
            "ovnis-pr",
            "admin-touch",
            polygon,
            "EPSG:6566",
            "REPORTED_MUNICIPALITY_EXTENT",
            ADMIN_METHOD,
            ADMIN_UNCERTAINTY,
            ADMIN_EVIDENCE_STATE,
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0235"
    ]


@pytest.mark.parametrize(
    ("method", "uncertainty", "evidence", "match"),
    [
        (ADMIN_METHOD, "EXACT", ADMIN_EVIDENCE_STATE, "ADMINISTRATIVE_ONLY"),
        (ADMIN_METHOD, ADMIN_UNCERTAINTY, DERIVED_EVIDENCE_STATE, ADMIN_EVIDENCE_STATE),
        (DERIVED_METHOD, ADMIN_UNCERTAINTY, DERIVED_EVIDENCE_STATE, "DERIVED"),
        (DERIVED_METHOD, DERIVED_UNCERTAINTY, ADMIN_EVIDENCE_STATE, DERIVED_EVIDENCE_STATE),
    ],
)
def test_method_uncertainty_and_evidence_must_match(method, uncertainty, evidence, match):
    row = {
        "Repository": "ovnis-pr",
        "Record_ID": "bad",
        "CRS": "EPSG:6566",
        "Binding_Method": method,
        "Uncertainty_Class": uncertainty,
        "Geometry_Evidence_State": evidence,
        "Geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [246500, 255250],
                    [247500, 255250],
                    [247500, 255750],
                    [246500, 255750],
                    [246500, 255250],
                ]
            ],
        },
    }
    with pytest.raises(GridV2Error, match=match):
        set_geometry_from_mapping(row)


def test_set_geometry_rejects_line_and_wrong_crs():
    base = {
        "Repository": "ovnis-pr",
        "Record_ID": "bad-shape",
        "CRS": "EPSG:6566",
        "Binding_Method": ADMIN_METHOD,
        "Uncertainty_Class": ADMIN_UNCERTAINTY,
        "Geometry_Evidence_State": ADMIN_EVIDENCE_STATE,
        "Geometry": {
            "type": "LineString",
            "coordinates": [[246100, 255500], [247900, 255500]],
        },
    }
    with pytest.raises(GridV2Error, match="unsupported geometry"):
        set_geometry_from_mapping(base)
    wrong = dict(base)
    wrong["CRS"] = "EPSG:4326"
    with pytest.raises(GridV2Error, match="wrong CRS"):
        set_geometry_from_mapping(wrong)


def test_duplicate_set_identity_fails_closed():
    row = {
        "Repository": "ovnis-pr",
        "Record_ID": "same",
        "CRS": "EPSG:6566",
        "Binding_Method": ADMIN_METHOD,
        "Uncertainty_Class": ADMIN_UNCERTAINTY,
        "Geometry_Evidence_State": ADMIN_EVIDENCE_STATE,
        "Geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [246500, 255250],
                    [247500, 255250],
                    [247500, 255750],
                    [246500, 255750],
                    [246500, 255250],
                ]
            ],
        },
    }
    with pytest.raises(GridV2Error, match="duplicate"):
        bind_set_geometries([row, row], level="L1")


def test_set_receipt_blocks_exact_claim_promotion():
    rows = [
        {
            "Repository": "ovnis-pr",
            "Record_ID": "admin",
            "CRS": "EPSG:6566",
            "Binding_Method": ADMIN_METHOD,
            "Uncertainty_Class": ADMIN_UNCERTAINTY,
            "Geometry_Evidence_State": ADMIN_EVIDENCE_STATE,
            "Geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [246500, 255250],
                        [247500, 255250],
                        [247500, 255750],
                        [246500, 255750],
                        [246500, 255250],
                    ]
                ],
            },
        },
        {
            "Repository": "moneysweep-pr",
            "Record_ID": "derived",
            "CRS": "EPSG:6566",
            "Binding_Method": DERIVED_METHOD,
            "Uncertainty_Class": DERIVED_UNCERTAINTY,
            "Geometry_Evidence_State": DERIVED_EVIDENCE_STATE,
            "Geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [246500, 255250],
                        [247500, 255250],
                        [247500, 255750],
                        [246500, 255750],
                        [246500, 255250],
                    ]
                ],
            },
        },
    ]
    results = bind_set_geometries(rows, level="L1")
    assert len(flatten_set_binding_rows(results)) == 4
    receipt = set_binding_receipt(results)
    assert receipt["Exact_Cell_Claim_Permitted"] is False
    assert receipt["Input_Record_Count"] == 2
    assert receipt["Binding_Row_Count"] == 4
    assert receipt["Binding_Method_Record_Counts"] == {
        ADMIN_METHOD: 1,
        DERIVED_METHOD: 1,
    }
    assert receipt["Uncertainty_Class_Record_Counts"] == {
        ADMIN_UNCERTAINTY: 1,
        DERIVED_UNCERTAINTY: 1,
    }
