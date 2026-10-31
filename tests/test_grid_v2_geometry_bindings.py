"""Certification tests for PR grid V2 polygon and line bindings."""

from __future__ import annotations

import pytest
from shapely.geometry import LineString, Polygon

from spiderweb.geographic_grid_v2 import GridV2Error
from spiderweb.grid_v2_geometry_bindings import (
    ExactGeometryRecord,
    bind_exact_geometries,
    bind_exact_line,
    bind_exact_polygon,
    exact_geometry_from_mapping,
    flatten_geometry_binding_rows,
    geometry_binding_receipt,
)


def test_polygon_inside_one_cell_emits_positive_area_binding():
    polygon = Polygon(
        [(246100, 255100), (246900, 255100), (246900, 255900), (246100, 255900)]
    )
    result = bind_exact_polygon(
        ExactGeometryRecord(
            "aguayluz-pr",
            "polygon-one",
            polygon,
            "EPSG:6566",
            "FACILITY_FOOTPRINT",
        ),
        level="L1",
    )
    assert len(result.bindings) == 1
    row = result.bindings[0]
    assert row["Cell_ID"] == "PRG2:L1:R075:C0234"
    assert row["Binding_Method"] == "INTERSECTS_POSITIVE_AREA"
    assert row["Overlap_Area_m2"] == pytest.approx(640000.0)
    assert row["Cell_Coverage_Fraction"] == pytest.approx(0.64)
    assert row["Length_In_Cell_m"] is None
    assert row["Geometry_State"] == "VERIFIED_PROJECTED_POLYGON"


def test_polygon_crossing_boundary_emits_two_positive_area_cells():
    polygon = Polygon(
        [(246500, 255250), (247500, 255250), (247500, 255750), (246500, 255750)]
    )
    result = bind_exact_polygon(
        ExactGeometryRecord(
            "aguayluz-pr",
            "polygon-cross",
            polygon,
            "EPSG:6566",
            "FACILITY_FOOTPRINT",
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]
    assert [row["Overlap_Area_m2"] for row in result.bindings] == pytest.approx(
        [250000.0, 250000.0]
    )


def test_polygon_touch_only_neighbor_does_not_bind():
    polygon = Polygon(
        [(247000, 255100), (247500, 255100), (247500, 255900), (247000, 255900)]
    )
    result = bind_exact_polygon(
        ExactGeometryRecord(
            "aguayluz-pr",
            "touch-only",
            polygon,
            "EPSG:6566",
            "FACILITY_FOOTPRINT",
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0235"
    ]


def test_line_crossing_cells_records_positive_length_per_cell():
    line = LineString([(246100, 255500), (247900, 255500)])
    result = bind_exact_line(
        ExactGeometryRecord(
            "skywatcher-pr",
            "flight-segment",
            line,
            "EPSG:6566",
            "TRACK_SEGMENT",
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]
    assert [row["Length_In_Cell_m"] for row in result.bindings] == pytest.approx(
        [900.0, 900.0]
    )
    assert all(row["Binding_Method"] == "LINE_POSITIVE_LENGTH" for row in result.bindings)


def test_line_corner_touch_does_not_create_zero_length_neighbor_binding():
    line = LineString([(246100, 255100), (247000, 256000)])
    result = bind_exact_line(
        ExactGeometryRecord(
            "skywatcher-pr",
            "corner-touch",
            line,
            "EPSG:6566",
            "TRACK_SEGMENT",
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0234"
    ]


def test_line_on_exact_grid_boundary_preserves_shared_cell_multiplicity():
    line = LineString([(247000, 255100), (247000, 255900)])
    result = bind_exact_line(
        ExactGeometryRecord(
            "skywatcher-pr",
            "boundary-line",
            line,
            "EPSG:6566",
            "TRACK_SEGMENT",
        ),
        level="L1",
    )
    assert [row["Cell_ID"] for row in result.bindings] == [
        "PRG2:L1:R075:C0234",
        "PRG2:L1:R075:C0235",
    ]
    assert [row["Length_In_Cell_m"] for row in result.bindings] == pytest.approx(
        [800.0, 800.0]
    )


def test_outside_geometry_emits_zero_bindings_but_receipt_preserves_record():
    polygon = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    result = bind_exact_polygon(
        ExactGeometryRecord(
            "aguayluz-pr",
            "outside",
            polygon,
            "EPSG:6566",
            "FACILITY_FOOTPRINT",
        ),
        level="L1",
    )
    assert result.bindings == ()
    receipt = geometry_binding_receipt([result])
    assert receipt["Input_Record_Count"] == 1
    assert receipt["Binding_Row_Count"] == 0
    assert receipt["Zero_Binding_Record_Count"] == 1


def test_mapping_parser_rejects_wrong_crs_uncertainty_and_invalid_geometry():
    base = {
        "Repository": "aguayluz-pr",
        "Record_ID": "x",
        "CRS": "EPSG:6566",
        "Uncertainty_Class": "EXACT",
        "Geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [246100, 255100],
                    [246900, 255100],
                    [246900, 255900],
                    [246100, 255900],
                    [246100, 255100],
                ]
            ],
        },
    }
    assert exact_geometry_from_mapping(base).geometry.geom_type == "Polygon"

    wrong_crs = dict(base, CRS="EPSG:4326")
    with pytest.raises(GridV2Error, match="wrong CRS"):
        exact_geometry_from_mapping(wrong_crs)

    approximate = dict(base, Uncertainty_Class="APPROXIMATE")
    with pytest.raises(GridV2Error, match="EXACT"):
        exact_geometry_from_mapping(approximate)

    point = dict(
        base,
        Geometry={"type": "Point", "coordinates": [246500, 255500]},
    )
    with pytest.raises(GridV2Error, match="unsupported geometry"):
        exact_geometry_from_mapping(point)


def test_duplicate_record_identity_fails_closed():
    row = {
        "Repository": "aguayluz-pr",
        "Record_ID": "same",
        "CRS": "EPSG:6566",
        "Geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [246100, 255100],
                    [246900, 255100],
                    [246900, 255900],
                    [246100, 255900],
                    [246100, 255100],
                ]
            ],
        },
    }
    with pytest.raises(GridV2Error, match="duplicate"):
        bind_exact_geometries([row, row], level="L1")


def test_receipt_and_flattened_denominators_are_deterministic():
    rows = [
        {
            "Repository": "aguayluz-pr",
            "Record_ID": "poly",
            "CRS": "EPSG:6566",
            "Spatial_Role": "FACILITY_FOOTPRINT",
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
            "Repository": "skywatcher-pr",
            "Record_ID": "line",
            "CRS": "EPSG:6566",
            "Spatial_Role": "TRACK_SEGMENT",
            "Geometry": {
                "type": "LineString",
                "coordinates": [[246100, 255500], [247900, 255500]],
            },
        },
    ]
    results = bind_exact_geometries(rows, level="L1")
    flat = flatten_geometry_binding_rows(results)
    assert len(flat) == 4
    receipt = geometry_binding_receipt(results)
    assert receipt["Migration_Provenance_Class"] == "RECOMPUTED_FROM_SOURCE_GEOMETRY"
    assert receipt["Input_Record_Count"] == 2
    assert receipt["Binding_Row_Count"] == 4
    assert receipt["Zero_Binding_Record_Count"] == 0
    assert receipt["Binding_Method_Counts"] == {
        "INTERSECTS_POSITIVE_AREA": 2,
        "LINE_POSITIVE_LENGTH": 2,
    }
    assert receipt["Geometry_Type_Counts"] == {
        "LineString": 1,
        "Polygon": 1,
    }
