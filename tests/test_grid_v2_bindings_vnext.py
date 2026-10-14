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
    assert receipt["Clipped_Traversal_Length_m"] == 800
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
    assert [r["State"] for r in receipt["Record_Outcomes"]] == ["OUTSIDE", "TOUCH_ONLY", "BOUND"]
    assert [r["Record_ID"] for r in receipt["Record_Outcomes"]] == ["p", "g", "l"]
    assert [r["Binding_Row_Count"] for r in receipt["Record_Outcomes"]] == [0, 0, 2]
    assert sum(r["Binding_Row_Count"] for r in receipt["Record_Outcomes"]) == receipt["Binding_Row_Count"]
    assert all(len(r["Input_Geometry_SHA256"]) == 64 for r in receipt["Record_Outcomes"])




def freeze_fixture_source(tmp_path, input_path):
    """Freeze byte-identical fixture snapshot, never assert external authority."""
    from spiderweb.grid_v2_source_snapshot import SOURCE_CONTRACT

    frozen = tmp_path / "snapshot_source.jsonl"
    raw = input_path.read_bytes()
    frozen.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    source_manifest = {
        "contract": SOURCE_CONTRACT,
        "source_manifestation_id": "fixture-immutable-input",
        "source_uri": "urn:spiderweb:test:immutable-input",
        "retrieval_utc": "2026-10-13T00:00:00Z",
        "snapshot_filename": frozen.name,
        "snapshot_sha256": digest,
        "snapshot_bytes": len(raw),
        "input_sha256": digest,
        "input_bytes": len(raw),
        "input_record_count": sum(bool(line.strip()) for line in raw.splitlines()),
        "transformation": "BYTE_IDENTICAL",
        "authority_evidence_state": "UNVERIFIED",
    }
    out = tmp_path / "source_snapshot_manifest.json"
    out.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")
    return out

def test_cli_smoke_and_hash_bound_receipt(tmp_path):
    import subprocess
    import sys

    payload = [
        record(polygon(247000, 255100, 247500, 255900), "polygon"),
        record(line((247000, 255100), (247000, 255900)), "line"),
        record({"type": "Point", "coordinates": [0, 0]}, "outside"),
    ]
    source = tmp_path / "source.jsonl"
    out = tmp_path / "bindings.jsonl"
    receipt_path = tmp_path / "receipt.json"
    source.write_text("".join(json.dumps(row) + "\n" for row in payload), encoding="utf-8")
    manifest = freeze_fixture_source(tmp_path, source)
    cmd = [
        sys.executable, "scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py",
        "--input", str(source), "--level", "L1",
        "--source-manifest", str(manifest),
        "--bindings-out", str(out), "--receipt-out", str(receipt_path),
    ]
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    saved = json.loads(receipt_path.read_text())
    assert saved["Input_Record_Count"] == 3
    assert saved["Binding_Row_Count"] == 3
    assert len(saved["Record_Outcomes"]) == 3
    assert saved["Record_Outcomes"][2]["Record_ID"] == "outside"
    assert saved["Record_Outcomes"][2]["State"] == "OUTSIDE"
    assert saved["Record_Outcomes"][2]["Binding_Row_Count"] == 0
    assert saved["State_Counts"] == {"BOUND": 2, "OUTSIDE": 1, "TOUCH_ONLY": 0}
    assert saved["Receipt_State"] == "PROVISIONAL"
    assert saved["Source_Provenance_State"] == "BYTE_VERIFIED_AUTHORITY_UNRESOLVED"
    assert saved["Source_Transformation"] == "BYTE_IDENTICAL"
    assert saved["Source_Authority_Evidence_State"] == "UNVERIFIED"
    assert saved["Binding_Output_SHA256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert saved["Binding_Output_Bytes"] == out.stat().st_size
    assert saved["Input_SHA256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    # Fail-closed negative: no new files if input is invalid.
    source.write_text(json.dumps(record(
        polygon(247000, 255100, 247500, 255900), "invalid",
        CRS="EPSG:4326"
    )) + "\n", encoding="utf-8")
    manifest = freeze_fixture_source(tmp_path, source)
    other = tmp_path / "forbidden.jsonl"
    negative = subprocess.run([
        sys.executable, "scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py",
        "--input", str(source), "--source-manifest", str(manifest),
        "--level", "L1",
        "--bindings-out", str(other),
        "--receipt-out", str(tmp_path / "forbidden-receipt.json"),
    ], cwd=ROOT, capture_output=True, text=True)
    assert negative.returncode != 0
    assert "FAIL_CLOSED" in negative.stderr
    assert not other.exists()
    assert not (tmp_path / "forbidden-receipt.json").exists()


def test_snapshot_manifest_negative_tampering_and_claims(tmp_path):
    from spiderweb.grid_v2_source_snapshot import (
        strict_json, verify_source_snapshot,
    )
    source = tmp_path / "in.jsonl"
    source.write_text(json.dumps(record(
        {"type": "Point", "coordinates": [246500, 255500]}
    )) + "\n", encoding="utf-8")
    manifest = freeze_fixture_source(tmp_path, source)
    receipt = verify_source_snapshot(manifest, source, record_count=1)
    assert receipt["Source_Provenance_State"] == "BYTE_VERIFIED_AUTHORITY_UNRESOLVED"
    doc = json.loads(manifest.read_text())
    doc["authority_evidence_state"] = "AUTHORITATIVE"
    manifest.write_text(json.dumps(doc))
    with pytest.raises(GridV2Error, match="authority"):
        verify_source_snapshot(manifest, source, record_count=1)
    doc["authority_evidence_state"] = "UNVERIFIED"
    manifest.write_text(json.dumps(doc))
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(GridV2Error, match="SHA256"):
        verify_source_snapshot(manifest, source, record_count=1)


def test_duplicate_json_object_keys_fail_closed(tmp_path):
    from spiderweb.grid_v2_source_snapshot import strict_json, verify_source_snapshot
    with pytest.raises(GridV2Error, match="duplicate JSON key"):
        strict_json('{"Repository":"a","Repository":"b"}')
    with pytest.raises(GridV2Error, match="duplicate JSON key"):
        strict_json('{"Geometry":{"type":"Point","type":"LineString"}}')
    with pytest.raises(GridV2Error, match="numeric constant"):
        strict_json('{"X":NaN}')
    source = tmp_path / "src.jsonl"
    source.write_text(json.dumps(record(
        {"type": "Point", "coordinates": [246500, 255500]}
    )) + "\n")
    manifest = freeze_fixture_source(tmp_path, source)
    manifest.write_text('{"contract":"x","contract":"y"}')
    with pytest.raises(GridV2Error, match="duplicate JSON key"):
        verify_source_snapshot(manifest, source, record_count=1)


def test_snapshot_row_denominator_and_missing_files_fail_closed(tmp_path):
    from spiderweb.grid_v2_source_snapshot import verify_source_snapshot
    source = tmp_path / "src.jsonl"
    source.write_text(json.dumps(record(
        {"type": "Point", "coordinates": [246500, 255500]}
    )) + "\n")
    manifest = freeze_fixture_source(tmp_path, source)
    with pytest.raises(GridV2Error, match="denominator"):
        verify_source_snapshot(manifest, source, record_count=2)
    frozen = tmp_path / "snapshot_source.jsonl"
    frozen.unlink()
    with pytest.raises((GridV2Error, FileNotFoundError)):
        verify_source_snapshot(manifest, source, record_count=1)


def test_source_manifest_rejects_unverified_transformation(tmp_path):
    from spiderweb.grid_v2_source_snapshot import verify_source_snapshot
    source = tmp_path / "src.jsonl"
    source.write_text(json.dumps(record(
        {"type": "Point", "coordinates": [246500, 255500]}
    )) + "\n")
    manifest = freeze_fixture_source(tmp_path, source)
    m = json.loads(manifest.read_text())
    m["transformation"] = "NORMALIZED_GEOMETRY"
    manifest.write_text(json.dumps(m))
    with pytest.raises(GridV2Error, match="transformation"):
        verify_source_snapshot(manifest, source, record_count=1)


def test_vnext_preserves_raw_record_identifiers_without_normalizing():
    point = {"type": "Point", "coordinates": [246500, 255500]}
    a = bind_exact_geometry(record(point, "  observed-ID  ", Repository=" source-pr "), level="L1")
    assert a.repository == " source-pr "
    assert a.record_id == "  observed-ID  "
    assert a.bindings[0]["Repository"] == " source-pr "
    assert a.bindings[0]["Record_ID"] == "  observed-ID  "
    # Exact raw identifiers are different identities; no name-only coalescing.
    result = bind_exact_geometries([
        record(point, "ID"), record(point, " ID ")
    ], level="L1")
    assert len(result) == 2


def test_cli_existing_outputs_immutable_and_exact_replay_idempotent(tmp_path):
    import subprocess
    import sys

    row = record({"type": "Point", "coordinates": [246500, 255500]})
    inp = tmp_path / "input.jsonl"
    inp.write_text(json.dumps(row) + "\n", encoding="utf-8")
    manifest = freeze_fixture_source(tmp_path, inp)
    out = tmp_path / "out.jsonl"
    receipt = tmp_path / "receipt.json"
    command = [
        sys.executable, "scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py",
        "--input", str(inp), "--source-manifest", str(manifest),
        "--level", "L1", "--bindings-out", str(out), "--receipt-out", str(receipt),
    ]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    preserved = (out.read_bytes(), receipt.read_bytes())
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert (out.read_bytes(), receipt.read_bytes()) == preserved
    # Tamper receipt: do not mutate existing binding nor overwrite the receipt.
    receipt.write_bytes(b"manually changed")
    third = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert third.returncode != 0
    assert "nonidentical overwrite" in third.stderr
    assert out.read_bytes() == preserved[0]
    assert receipt.read_bytes() == b"manually changed"


def test_cli_rejects_output_colliding_with_source_snapshot(tmp_path):
    import subprocess
    import sys

    row = record({"type": "Point", "coordinates": [246500, 255500]})
    inp = tmp_path / "input.jsonl"
    inp.write_text(json.dumps(row) + "\n", encoding="utf-8")
    manifest = freeze_fixture_source(tmp_path, inp)
    frozen = tmp_path / "snapshot_source.jsonl"
    original_bytes = frozen.read_bytes()
    proc = subprocess.run([
        sys.executable, "scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py",
        "--input", str(inp), "--source-manifest", str(manifest), "--level", "L1",
        "--bindings-out", str(frozen), "--receipt-out", str(tmp_path / "receipt.json"),
    ], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "frozen source snapshot" in proc.stderr
    assert frozen.read_bytes() == original_bytes


def test_retraced_route_length_is_not_distinct_spatial_support():
    result = bind_exact_geometry(record(line(
        (246500, 255500), (247500, 255500), (246500, 255500)
    )), level="L1")
    receipt = binding_receipt_vnext([result])
    assert receipt["Clipped_Traversal_Length_m"] == 2000.0
    assert receipt["Distinct_Clipped_Spatial_Support_Length_m"] == 1000.0
    assert receipt["Retraversed_Spatial_Length_m"] == 1000.0
    assert receipt["Cell_Bound_Length_Sum_m"] == 2000.0
    assert receipt["Grid_Edge_Length_Multiplicity_m"] == 0.0


def test_outside_line_has_explicit_outcome_and_zero_support():
    result = bind_exact_geometry(record(line((0, 0), (100, 100))), level="L1")
    receipt = binding_receipt_vnext([result])
    assert receipt["State_Counts"] == {"BOUND": 0, "OUTSIDE": 1, "TOUCH_ONLY": 0}
    assert receipt["Record_Outcomes"][0]["State"] == "OUTSIDE"
    assert receipt["Binding_Row_Count"] == 0
    assert receipt["Clipped_Traversal_Length_m"] == 0
    assert receipt["Distinct_Clipped_Spatial_Support_Length_m"] == 0


def test_independent_artifact_audit_success_and_tamper(tmp_path):
    import subprocess
    import sys
    from spiderweb.grid_v2_binding_artifact_audit import audit_binding_artifacts

    points = [
        record({"type": "Point", "coordinates": [247000, 255500]}, "edge"),
        record(polygon(247000, 255100, 247500, 255900), "polygon"),
        record(line((247000, 255100), (247000, 255900)), "line"),
        record({"type": "Point", "coordinates": [0, 0]}, "outside"),
    ]
    source = tmp_path / "source.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in points), encoding="utf-8")
    frozen_manifest = freeze_fixture_source(tmp_path, source)
    out = tmp_path / "bindings.jsonl"
    receipt = tmp_path / "receipt.json"
    p = subprocess.run([
        sys.executable, "scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py",
        "--input", str(source), "--source-manifest", str(frozen_manifest),
        "--level", "L1", "--bindings-out", str(out), "--receipt-out", str(receipt)
    ], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode == 0, p.stderr
    audit = audit_binding_artifacts(
        input_path=source, manifest_path=frozen_manifest,
        bindings_path=out, receipt_path=receipt,
    )
    assert audit["Audit_State"] == "PASS"
    assert audit["Certification_State"] == "AUDIT_ONLY"
    assert audit["Consumer_Activation"] == "BLOCKED_UNTIL_CERTIFIED"
    assert audit["Input_Record_Count"] == 4
    assert audit["Binding_Row_Count"] == 5
    # CLI verification is a separate process from materialization.
    q = subprocess.run([
        sys.executable, "scripts/audit_pr_grid_v2_binding_artifacts.py",
        "--input", str(source), "--source-manifest", str(frozen_manifest),
        "--bindings", str(out), "--receipt", str(receipt),
    ], cwd=ROOT, text=True, capture_output=True)
    assert q.returncode == 0, q.stderr
    assert json.loads(q.stdout)["Certification_State"] == "AUDIT_ONLY"
    untouched = out.read_bytes()

    # Hash-bound bytes: single-byte tamper must fail.
    out.write_bytes(untouched + b" ")
    with pytest.raises(GridV2Error, match="SHA256"):
        audit_binding_artifacts(input_path=source, manifest_path=frozen_manifest,
                                bindings_path=out, receipt_path=receipt)
    out.write_bytes(untouched)

    # Recompute receipt hash as an adversarial tampering simulation.
    fake_rows = out.read_text(encoding="utf-8").splitlines()
    forged = json.loads(fake_rows[0])
    forged["Cell_ID"] = "PRG2:L1:R999:C9999"
    fake_rows[0] = json.dumps(forged, sort_keys=True, separators=(",", ":"))
    forged_bytes = ("\n".join(fake_rows) + "\n").encode("utf-8")
    out.write_bytes(forged_bytes)
    audit_receipt = json.loads(receipt.read_text())
    audit_receipt["Binding_Output_SHA256"] = hashlib.sha256(forged_bytes).hexdigest()
    audit_receipt["Binding_Output_Bytes"] = len(forged_bytes)
    receipt.write_text(json.dumps(audit_receipt), encoding="utf-8")
    with pytest.raises(GridV2Error, match="cell out of range"):
        audit_binding_artifacts(input_path=source, manifest_path=frozen_manifest,
                                bindings_path=out, receipt_path=receipt)


def test_independent_audit_detects_receipt_level_tamper(tmp_path):
    import subprocess
    import sys
    from spiderweb.grid_v2_binding_artifact_audit import audit_binding_artifacts

    source = tmp_path / "input.jsonl"
    source.write_text(json.dumps(record(
        {"type": "Point", "coordinates": [246500, 255500]}
    )) + "\n", encoding="utf-8")
    manifest = freeze_fixture_source(tmp_path, source)
    out = tmp_path / "bindings.jsonl"
    receipt = tmp_path / "receipt.json"
    run = subprocess.run([
        sys.executable, "scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py",
        "--input", str(source), "--source-manifest", str(manifest),
        "--level", "L1", "--bindings-out", str(out), "--receipt-out", str(receipt)
    ], cwd=ROOT, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    payload = json.loads(receipt.read_text())
    payload["Grid_Level"] = "L2"
    receipt.write_text(json.dumps(payload))
    with pytest.raises(GridV2Error, match="Grid_Level"):
        audit_binding_artifacts(input_path=source, manifest_path=manifest,
                                bindings_path=out, receipt_path=receipt)
