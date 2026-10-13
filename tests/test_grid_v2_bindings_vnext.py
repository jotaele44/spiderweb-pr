"""Positive/negative certification candidates for vNext projected bindings."""
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from spiderweb.geographic_grid_v2 import GridV2Error
from spiderweb.grid_v2_bindings import ExactPointRecord, bind_exact_point
from spiderweb.grid_v2_bindings_vnext import (
    BINDING_SCHEMA_SHA256, BINDING_VERSION, RC1_BINDING_SCHEMA_SHA256,
    bind_exact_geometries, bind_exact_geometry, binding_receipt_vnext,
    validate_schema_pins,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/pr_grid_geographic_v2_binding_vnext.schema.json"


def record(geometry, record_id="a", **overrides):
    value = dict(Repository="aguayluz-pr", Record_ID=record_id,
                 CRS="EPSG:6566", Uncertainty_Class="EXACT", Geometry=geometry)
    value.update(overrides)
    return value


def polygon(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]
    ]]}


def line(*points):
    return {"type": "LineString", "coordinates": [list(p) for p in points]}


def test_vnext_pins_and_rc1_are_immutable():
    validate_schema_pins()
    assert hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest() == BINDING_SCHEMA_SHA256
    assert hashlib.sha256((ROOT / "schemas/pr_grid_geographic_v2_binding.schema.json").read_bytes()).hexdigest() == RC1_BINDING_SCHEMA_SHA256


@pytest.mark.parametrize("geometry,expected_state,expected_ids", [
    ({"type": "Point", "coordinates": [246500, 255500]}, "INTERIOR", ["PRG2:L1:R075:C0234"]),
    ({"type": "Point", "coordinates": [247000, 255500]}, "EDGE_SHARED", ["PRG2:L1:R075:C0234", "PRG2:L1:R075:C0235"]),
    ({"type": "Point", "coordinates": [247000, 256000]}, "CORNER_SHARED", [
        "PRG2:L1:R075:C0234", "PRG2:L1:R075:C0235",
        "PRG2:L1:R076:C0234", "PRG2:L1:R076:C0235"
    ]),
])
def test_point_rc1_semantics_remain_exact(geometry, expected_state, expected_ids):
    got = bind_exact_geometry(record(geometry), level="L1")
    legacy = bind_exact_point(ExactPointRecord(
        "aguayluz-pr", "a", *geometry["coordinates"], "EPSG:6566"
    ), level="L1")
    assert got.state == "BOUND"
    assert [b["Cell_ID"] for b in got.bindings] == expected_ids
    assert [b["Cell_ID"] for b in legacy.bindings] == expected_ids
    assert all(b["Point_Boundary_State"] == expected_state for b in got.bindings)


def test_outside_point_has_explicit_receipt_no_cell():
    got = bind_exact_geometry(record({"type": "Point", "coordinates": [0, 0]}), level="L1")
    assert got.state == "OUTSIDE" and not got.bindings


def test_polygon_area_membership_and_touch_only_exclusion():
    got = bind_exact_geometry(record(polygon(247000, 255100, 247500, 255900)), level="L1")
    assert len(got.bindings) == 1
    b = got.bindings[0]
    assert b["Cell_ID"] == "PRG2:L1:R075:C0235"
    assert b["Overlap_Area_m2"] == 400000
    assert b["Cell_Coverage_Fraction"] == 0.4
    assert b["Point_Boundary_State"] is None


def test_polygon_crosses_four_cells_area_conservation():
    got = bind_exact_geometry(record(polygon(246500, 255500, 247500, 256500)), level="L1")
    assert len(got.bindings) == 4
    assert sum(b["Overlap_Area_m2"] for b in got.bindings) == 1000000
    assert all(b["Overlap_Area_m2"] > 0 for b in got.bindings)


def test_polygon_touch_only_at_outer_grid_has_no_binding():
    got = bind_exact_geometry(record(polygon(354000, 255100, 354500, 255900)), level="L1")
    assert got.state == "TOUCH_ONLY"
    assert not got.bindings


def test_polygon_hole_is_not_filled_in():
    geom = {"type": "Polygon", "coordinates": [
        [[246000, 255000], [249000, 255000], [249000, 258000], [246000, 258000], [246000, 255000]],
        [[247000, 256000], [248000, 256000], [248000, 257000], [247000, 257000], [247000, 256000]],
    ]}
    got = bind_exact_geometry(record(geom), level="L1")
    assert "PRG2:L1:R076:C0235" not in [r["Cell_ID"] for r in got.bindings]


def test_line_crossing_point_only_corner_contacts_excluded():
    got = bind_exact_geometry(record(line((246500, 255500), (247500, 256500))), level="L1")
    assert len(got.bindings) == 2
    assert {r["Cell_ID"] for r in got.bindings} == {
        "PRG2:L1:R075:C0234", "PRG2:L1:R076:C0235"
    }
    assert all(r["Length_In_Cell_m"] > 0 for r in got.bindings)


def test_line_on_grid_edge_binds_both_and_marks_nonadditive_length():
    got = bind_exact_geometry(record(line((247000, 255100), (247000, 255900))), level="L1")
    assert len(got.bindings) == 2
    assert all(r["Boundary_Coincident"] is True for r in got.bindings)
    assert all(r["Length_In_Cell_m"] == 800 for r in got.bindings)
    receipt = binding_receipt_vnext([got])
    assert receipt["Unique_Clipped_Traversal_Length_m"] == 800
    assert receipt["Cell_Bound_Length_Sum_m"] == 1600
    assert receipt["Grid_Edge_Length_Multiplicity_m"] == 800


def test_line_reenter_same_cell_keeps_distinct_traversal_episodes():
    got = bind_exact_geometry(record(line((246500, 255500), (247500, 255500),
                                         (246500, 255500))), level="L1")
    assert len(got.bindings) == 4
    assert [r["Traversal_Order"] for r in got.bindings] == [0, 1, 2, 3]
    assert [r["Segment_Index"] for r in got.bindings] == [0, 0, 1, 1]
    assert len({r["Cell_ID"] for r in got.bindings}) == 2


def test_multiline_preserves_component_order():
    geom = {"type": "MultiLineString", "coordinates": [
        [[246500, 255500], [247500, 255500]],
        [[247500, 255500], [246500, 255500]],
    ]}
    got = bind_exact_geometry(record(geom), level="L1")
    assert len(got.bindings) == 4
    assert [r["Component_Index"] for r in got.bindings] == [0, 0, 1, 1]


@pytest.mark.parametrize("modification", [
    {"CRS": ""}, {"CRS": "EPSG:4326"}, {"Uncertainty_Class": "DERIVED"},
    {"Grid_ID": "WRONG"}, {"Grid_Version": "2.0.0"},
    {"Grid_Manifest_SHA256": "0" * 64},
])
def test_reject_wrong_input_identity_crs_precision(modification):
    with pytest.raises(GridV2Error):
        bind_exact_geometry(record(polygon(246500, 255500, 247500, 256500),
                                   **modification), level="L1")


@pytest.mark.parametrize("bad", [
    {"type": "Point", "coordinates": [246500, 255500, 0]},
    {"type": "Point", "coordinates": [246500, float("nan")]},
    {"type": "LineString", "coordinates": [[246500, 255500], [246500, 255500]]},
    {"type": "GeometryCollection", "geometries": []},
    {"type": "Polygon", "coordinates": [[[246500, 255500], [247500, 256500],
                                         [246500, 256500], [247500, 255500],
                                         [246500, 255500]]]},
])
def test_reject_invalid_empty_or_3d_geometry(bad):
    with pytest.raises(GridV2Error):
        bind_exact_geometry(record(bad), level="L1")


def test_duplicate_identity_across_geometry_types_fails_closed():
    with pytest.raises(GridV2Error, match="duplicate"):
        bind_exact_geometries([
            record({"type": "Point", "coordinates": [246500, 255500]}),
            record(line((246500, 255500), (247500, 255500))),
        ], level="L1")


def test_json_schema_positive_and_negative_constraints():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    cases = [
        record({"type": "Point", "coordinates": [247000, 256000]}, "p"),
        record(polygon(246500, 255500, 247500, 256500), "g"),
        record(line((247000, 255100), (247000, 255900)), "l"),
    ]
    bound = [b for result in bind_exact_geometries(cases, level="L1") for b in result.bindings]
    assert bound
    for row in bound:
        assert row["Binding_Version"] == BINDING_VERSION
        assert not list(validator.iter_errors(row))
    for name, mutation in [
        ("wrong_relation", {"Spatial_Relation": "POINT_COVERED"}),
        ("zero_length", {"Length_In_Cell_m": 0}),
        ("fake_point_boundary", {"Point_Boundary_State": "EDGE_SHARED"}),
        ("missing_order", {"Traversal_Order": None}),
        ("invalid_cell", {"Cell_ID": "PRG2:L1:R999:C9999"}),
    ]:
        broken = dict(next(b for b in bound if b["Source_Geometry_Type"] == "LINE"))
        broken.update(mutation)
        if name != "invalid_cell":
            assert list(validator.iter_errors(broken)), name
        else:
            # Regex schema cannot constrain per-level coordinates: runtime gate must.
            from spiderweb.geographic_grid_v2 import parse_cell_id
            with pytest.raises(GridV2Error):
                parse_cell_id(broken["Cell_ID"])


def test_schema_pin_mutation_fails_closed(tmp_path):
    paths = [
        "schemas/pr_grid_geographic_v2_binding_vnext.schema.json",
        "schemas/pr_grid_geographic_v2_binding.schema.json",
        "registry/spatial/v2/pr_grid_geographic_v2_binding_vnext.manifest.json",
        "registry/spatial/v2/pr_grid_geographic_v2.manifest.json",
    ]
    for rel in paths:
        to = tmp_path / rel
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_bytes((ROOT / rel).read_bytes())
    validate_schema_pins(tmp_path)
    p = tmp_path / paths[0]
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(GridV2Error, match="SHA256"):
        validate_schema_pins(tmp_path)


def test_denominator_and_touch_outside_conservation():
    rows = [
        record({"type": "Point", "coordinates": [0, 0]}, "p"),
        record(polygon(354000, 255100, 354500, 255900), "g"),
        record(line((247000, 255100), (247000, 255900)), "l"),
    ]
    receipt = binding_receipt_vnext(bind_exact_geometries(rows, level="L1"))
    assert receipt["Input_Record_Count"] == 3
    assert receipt["Binding_Row_Count"] == 2
    assert receipt["State_Counts"] == {"BOUND": 1, "OUTSIDE": 1, "TOUCH_ONLY": 1}
    assert receipt["Certification_State"] == "PROVISIONAL"
    assert receipt["Consumer_Activation"] == "BLOCKED_UNTIL_CERTIFIED"
