"""Certification tests for authoritative PR grid V2 exact-point bindings."""

from __future__ import annotations

import pytest

from spiderweb.geographic_grid_v2 import BoundaryState, GridV2Error
from spiderweb.grid_v2_bindings import (
    ExactPointRecord,
    bind_exact_point,
    bind_exact_points,
    binding_receipt,
    flatten_binding_rows,
)


def test_interior_point_emits_one_binding():
    result = bind_exact_point(
        ExactPointRecord("aguayluz-pr", "gauge-1", 246500, 255500, "EPSG:6566"),
        level="L1",
    )
    assert result.state is BoundaryState.INTERIOR
    assert len(result.bindings) == 1
    row = result.bindings[0]
    assert row["Cell_ID"] == "PRG2:L1:R075:C0234"
    assert row["Binding_State"] == "INTERIOR"
    assert row["Binding_Method"] == "COVERS"
    assert row["Uncertainty_Class"] == "EXACT"
    assert row["Confidence"] == 1.0


def test_edge_point_preserves_two_bindings():
    result = bind_exact_point(
        ExactPointRecord("aguayluz-pr", "gauge-edge", 247000, 255500, "EPSG:6566"),
        level="L1",
    )
    assert result.state is BoundaryState.EDGE_SHARED
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]


def test_corner_point_preserves_four_bindings():
    result = bind_exact_point(
        ExactPointRecord("aguayluz-pr", "gauge-corner", 247000, 256000, "EPSG:6566"),
        level="L1",
    )
    assert result.state is BoundaryState.CORNER_SHARED
    assert len(result.bindings) == 4


def test_outside_point_emits_no_binding_but_remains_in_receipt():
    result = bind_exact_point(
        ExactPointRecord("aguayluz-pr", "outside", 0, 0, "EPSG:6566"),
        level="L1",
    )
    assert result.state is BoundaryState.OUTSIDE
    assert result.bindings == ()
    receipt = binding_receipt([result])
    assert receipt["Input_Record_Count"] == 1
    assert receipt["Binding_Row_Count"] == 0
    assert receipt["State_Counts"] == {"OUTSIDE": 1}


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:26919", ""])
def test_wrong_or_missing_crs_fails_closed(crs):
    with pytest.raises(GridV2Error):
        bind_exact_point(
            ExactPointRecord("aguayluz-pr", "bad-crs", 246500, 255500, crs),
            level="L1",
        )


def test_non_exact_uncertainty_fails_closed():
    with pytest.raises(GridV2Error, match="EXACT"):
        bind_exact_point(
            ExactPointRecord(
                "aguayluz-pr",
                "approx",
                246500,
                255500,
                "EPSG:6566",
                uncertainty_class="APPROXIMATE",
            ),
            level="L1",
        )


def test_duplicate_record_identity_fails_closed():
    rows = [
        {"Repository": "aguayluz-pr", "Record_ID": "same", "X": 246500, "Y": 255500, "CRS": "EPSG:6566"},
        {"Repository": "aguayluz-pr", "Record_ID": "same", "X": 246600, "Y": 255600, "CRS": "EPSG:6566"},
    ]
    with pytest.raises(GridV2Error, match="duplicate"):
        bind_exact_points(rows, level="L1")


def test_batch_receipt_preserves_record_and_binding_denominators():
    rows = [
        {"Repository": "aguayluz-pr", "Record_ID": "a", "X": 246500, "Y": 255500, "CRS": "EPSG:6566"},
        {"Repository": "aguayluz-pr", "Record_ID": "b", "X": 247000, "Y": 255500, "CRS": "EPSG:6566"},
        {"Repository": "aguayluz-pr", "Record_ID": "c", "X": 0, "Y": 0, "CRS": "EPSG:6566"},
    ]
    results = bind_exact_points(rows, level="L1")
    assert len(flatten_binding_rows(results)) == 3
    receipt = binding_receipt(results)
    assert receipt["Input_Record_Count"] == 3
    assert receipt["Binding_Row_Count"] == 3
    assert receipt["State_Counts"] == {
        "EDGE_SHARED": 1,
        "INTERIOR": 1,
        "OUTSIDE": 1,
    }


def test_binding_receipt_carries_frozen_authority_hash():
    from spiderweb.grid_v2_bindings import GRID_MANIFEST_SHA256

    result = bind_exact_point(
        ExactPointRecord("aguayluz-pr", "hash-proof", 246500, 255500, "EPSG:6566"),
        level="L1",
    )
    receipt = binding_receipt([result])
    assert receipt["Grid_Manifest_SHA256"] == GRID_MANIFEST_SHA256
    assert receipt["Grid_Manifest_SHA256"] == (
        "8902af188ad449955119016f5747fe2393c582d9ed552fb03bcaecd9ab510aa4"
    )
