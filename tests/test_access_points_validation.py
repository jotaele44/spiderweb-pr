"""Reference maps held by hash, and the detector compared with one.

Synthetic surfaces with planted basins stand in for the survey; outlines drawn
at the planted places stand in for the published map.  The last group
recomputes the committed comparison from the evidence kept in the repository.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from shapely.geometry import Point, mapping

from gebco.marine_evidence import VerticalReference
from spiderweb.access_points import controls, seeding, survey_run, validation
from spiderweb.access_points import detection as det
from spiderweb.access_points import reference as refsets
from spiderweb.access_points import vocabulary as v
from spiderweb.access_points.raster import SurfaceKind, make_grid

pytest.importorskip("rasterio")

REPO = Path(__file__).resolve().parents[1]
CRS = "EPSG:26919"
WEST, NORTH = 722000.0, 2033000.0
SHA = "0" * 64


def surface(basins, *, rows=400, cols=400, nodata_block=None):
    values = controls.tilted_plane(
        rows, cols, base_m=200.0, slope_x=0.01, slope_y=0.005
    )
    for row, col, depth, sigma in basins:
        values = controls.add_gaussian_basin(
            values, row, col, depth_m=depth, sigma_cells=sigma
        )
    if nodata_block is not None:
        r0, r1, c0, c1 = nodata_block
        values[r0:r1, c0:c1] = float("nan")
    return make_grid(
        values,
        cell_size_m=(1.0, 1.0),
        origin=(WEST, NORTH),
        crs=CRS,
        kind=SurfaceKind.TERRAIN_BARE_EARTH,
        vertical_reference=VerticalReference(CRS, None, "PRVD02", None, "up"),
        uncertainty_m=0.05,
        source_id="APSRC-" + "a" * 16,
    )


def label_set(**changes):
    base = dict(
        set_id="test_labels",
        role=refsets.ReferenceRole.LABELS,
        format=refsets.ReferenceFormat.GEOJSON,
        sha256=SHA,
        provider="TEST_MAP",
        title="synthetic sinkhole map",
        held=True,
        path="labels.geojson",
        bound_crs=CRS,
        crs_basis="test",
        positional_offset_m=20.0,
        positional_basis="test",
        label_class="SINKHOLE",
        stated_min_depth_m=3.0,
        received_utc="2026-11-15T00:00:00Z",
    )
    base.update(changes)
    return refsets.ReferenceSet(**base)


def layer_at(cells, radius=12.0, **changes):
    """Outlines centred on (row, col) cells of the test grid."""

    ref = label_set(**changes)
    features = tuple(
        refsets.ReferenceFeature(
            f"{ref.set_id}:{i + 1}",
            {},
            Point(WEST + col + 0.5, NORTH - row - 0.5).buffer(radius),
            False,
        )
        for i, (row, col) in enumerate(cells)
    )
    return refsets.ReferenceLayer(ref, features, len(features), 0, 0, False)


def detect(grid):
    source = sup_source()
    return det.detect_inland(
        grid, source, det.DetectionParameters(min_depth_m=1.0, min_area_m2=50.0)
    )


def sup_source():
    from tests import access_points_support as sup

    return sup.direct_source("TEST-GRID-1")


def scored(grid, layer, offset=150.0):
    labels, counts = validation.labels_for_grid(layer, grid)
    return (
        validation.score(
            detect(grid),
            labels,
            layer.ref,
            grid=grid,
            source_id="APSRC-" + "b" * 16,
            thresholds=[1, 3, 10],
            displaced_offset_m=offset,
        ),
        counts,
    )


# ── A map reference is not field truth ───────────────────────────────────────


def test_a_published_map_is_compared_with_never_measured_against():
    grid = surface([(100, 100, 5.0, 10.0)])
    detections = detect(grid)

    def label(kind):
        return det.ReferenceLabel(
            "L1", "SINKHOLE", (WEST + 100.5, NORTH - 100.5), 30.0, kind
        )

    report = det.evaluate(
        detections,
        [label(det.TruthKind.PUBLISHED_MAP_REFERENCE)],
        class_sensitive=False,
    )
    assert report.state is det.EvaluationState.REFERENCE_COMPARED
    assert "not field-verified" in report.statement and len(report.matched) == 1
    field = det.evaluate(
        detections,
        [label(det.TruthKind.INDEPENDENT_FIELD_TRUTH)],
        class_sensitive=False,
    )
    assert field.state is det.EvaluationState.MEASURED
    mixed = [
        label(det.TruthKind.PUBLISHED_MAP_REFERENCE),
        det.ReferenceLabel(
            "L2",
            "SINKHOLE",
            (WEST + 5, NORTH - 5),
            5.0,
            det.TruthKind.INDEPENDENT_FIELD_TRUTH,
        ),
    ]
    with pytest.raises(ValueError, match="scored separately"):
        det.evaluate(detections, mixed, class_sensitive=False)


# ── Reference sets: bytes and coordinate system ──────────────────────────────


def _config(tmp_path, entry):
    path = tmp_path / "sets.yaml"
    path.write_text(
        yaml.safe_dump({"version": refsets.REFERENCE_VERSION, "sets": [entry]}),
        encoding="utf-8",
    )
    return path


def _entry(tmp_path, features, **changes):
    document = {"type": "FeatureCollection", "crs": None, "features": features}
    data = json.dumps(document).encode()
    (tmp_path / "layer.geojson").write_bytes(data)
    entry = {
        "set_id": "t",
        "role": "LABELS",
        "format": "geojson",
        "held": True,
        "path": "layer.geojson",
        "sha256": refsets.sha256_bytes(data),
        "provider": "TEST_MAP",
        "title": "test",
        "bound_crs": CRS,
        "crs_basis": "stated in the test",
        "positional_offset_m": 10,
        "positional_basis": "stated in the test",
        "label_class": "SINKHOLE",
        "received_utc": "2026-11-15T00:00:00Z",
    }
    entry.update(changes)
    return entry


def _feature(geometry, oid=1):
    return {
        "type": "Feature",
        "properties": {"OBJECTID": oid},
        "geometry": mapping(geometry),
    }


def test_a_set_is_read_only_if_its_bytes_and_its_coordinates_fit(tmp_path):
    projected = _feature(Point(WEST + 50, NORTH - 50).buffer(10))
    entry = _entry(tmp_path, [projected])
    (ref,) = refsets.load_sets(_config(tmp_path, entry)).values()
    layer = refsets.read_layer(ref, tmp_path)
    assert len(layer.features) == 1 and layer.file_declares_crs is False
    assert not refsets.to_source(ref).is_direct_measurement

    (tmp_path / "layer.geojson").write_bytes(
        (tmp_path / "layer.geojson").read_bytes() + b" "
    )
    with pytest.raises(
        refsets.ReferenceSetError, match="do not match the declared hash"
    ):
        refsets.read_layer(ref, tmp_path)

    # Projected metres bound to longitude/latitude, and the reverse, are refused.
    wrong = _entry(tmp_path, [projected], bound_crs="OGC:CRS84")
    (ref,) = refsets.load_sets(_config(tmp_path, wrong)).values()
    with pytest.raises(refsets.ReferenceSetError, match="not longitude and latitude"):
        refsets.read_layer(ref, tmp_path)
    geographic = _entry(tmp_path, [_feature(Point(-66.9, 18.37).buffer(0.001))])
    (ref,) = refsets.load_sets(_config(tmp_path, geographic)).values()
    with pytest.raises(refsets.ReferenceSetError, match="look like longitude"):
        refsets.read_layer(ref, tmp_path)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"crs_basis": " "}, "bind a CRS"),
        ({"bound_crs": None}, "bind a CRS"),
        ({"positional_basis": None}, "positional"),
        ({"positional_offset_m": -1}, "negative"),
        ({"label_class": None}, "name their class"),
        ({"received_utc": None}, "when its bytes were received"),
        ({"sha256": "abc"}, "64 lowercase hex"),
        ({"role": "TRUTH"}, "unknown role"),
        ({"path": None}, "name its file"),
    ],
)
def test_an_incomplete_declaration_is_refused(tmp_path, change, message):
    entry = _entry(
        tmp_path, [_feature(Point(WEST + 50, NORTH - 50).buffer(10))], **change
    )
    with pytest.raises(refsets.ReferenceSetError, match=message):
        refsets.load_sets(_config(tmp_path, entry))


def test_a_set_recorded_by_hash_only_is_never_read(tmp_path):
    entry = {
        "set_id": "pointer",
        "role": "LINEAGE_ONLY",
        "format": "opaque",
        "held": False,
        "sha256": SHA,
        "provider": "TEST_MAP",
        "title": "a pointer",
    }
    (ref,) = refsets.load_sets(_config(tmp_path, entry)).values()
    with pytest.raises(refsets.ReferenceSetError, match="hash only"):
        refsets.read_layer(ref, tmp_path)
    with pytest.raises(refsets.ReferenceSetError, match="not held"):
        refsets.to_source(ref)
    escape = _entry(
        tmp_path, [_feature(Point(WEST, NORTH).buffer(5))], path="../x.geojson"
    )
    (ref,) = refsets.load_sets(_config(tmp_path, escape)).values()
    with pytest.raises(refsets.ReferenceSetError, match="inside the repository"):
        refsets.read_layer(ref, tmp_path)


def test_a_shapefile_whose_projection_names_another_system_is_refused(tmp_path):
    sets = refsets.load_sets(REPO / refsets.REFERENCE_PATH)
    limit = sets["pr_planning_board_northern_karst_limit"]
    layer = refsets.read_layer(limit, REPO)
    assert len(layer.features) == 1 and layer.file_declares_crs is True
    assert layer.features[0].geometry.area / 1e6 == pytest.approx(2187.0, abs=1.0)

    original = (REPO / limit.path).read_bytes()
    rebuilt = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as src,
        zipfile.ZipFile(rebuilt, "w") as dst,
    ):
        for name in src.namelist():
            data = src.read(name)
            if name.endswith(".prj"):
                data = data.replace(b'"EPSG","6566"', b'"EPSG","32161"')
            dst.writestr(name, data)
    (tmp_path / "limit.zip").write_bytes(rebuilt.getvalue())
    entry = {
        "set_id": "limit",
        "role": "KARST_LIMIT",
        "format": "shapefile_zip",
        "held": True,
        "path": "limit.zip",
        "sha256": refsets.sha256_bytes(rebuilt.getvalue()),
        "provider": "TEST_MAP",
        "title": "limit",
        "bound_crs": "EPSG:6566",
        "crs_basis": "the projection file",
        "received_utc": "2026-11-15T00:00:00Z",
    }
    (ref,) = refsets.load_sets(_config(tmp_path, entry)).values()
    with pytest.raises(refsets.ReferenceSetError, match="does not name EPSG:6566"):
        refsets.read_layer(ref, tmp_path)


# ── The comparison on surfaces with known answers ────────────────────────────


def test_planted_basins_are_found_and_displaced_outlines_are_not():
    grid = surface([(100, 100, 6.0, 9.0), (280, 250, 4.0, 8.0)])
    result, counts = scored(grid, layer_at([(100, 100), (280, 250)]))
    assert counts["scored"] == 2 and result["evaluation_state"] == "REFERENCE_COMPARED"
    first = result["object_detection_by_depth_threshold"][0]
    assert first["labels_found"] == 2 and first["displaced_found"] == 0
    assert (
        result["object_detection_by_depth_threshold"][-1]["labels_found"] == 0
    )  # none is 10 m deep
    surface_rows = result["surface_agreement"]["by_depth_threshold"]
    assert (
        surface_rows[0]["fraction"] == 1.0
        and surface_rows[0]["displaced_fraction"] == 0.0
    )
    assert surface_rows[1]["outlines_on_a_depression"] == 2  # both at least 3 m
    assert result["matched_basin_depth_m"]["at_least_stated_depth"] == 2
    assert result["precision"] is None and "not an error" in result["precision_note"]
    assert result["labels_missed"] == []


def test_a_sinkhole_nested_in_a_larger_basin_shows_in_the_surface_not_as_an_object():
    # One broad, shallow basin with two deep pits inside it: the fill raises
    # the whole basin to one spill level, so the detector reports one object.
    grid = surface([(200, 200, 3.0, 60.0), (190, 150, 8.0, 6.0), (210, 250, 8.0, 6.0)])
    result, _ = scored(grid, layer_at([(190, 150), (210, 250)], radius=10.0))
    objects = result["object_detection_by_depth_threshold"][0]
    assert objects["labels"] == 2 and objects["labels_found"] < 2
    assert result["labels_missed_by_reason"].get("INSIDE_A_LARGER_BASIN", 0) >= 1
    surface_row = result["surface_agreement"]["by_depth_threshold"][1]
    assert surface_row["outlines_on_a_depression"] == 2  # both pits are there


def test_a_map_that_puts_sinkholes_on_a_plane_scores_nothing():
    grid = surface([])
    result, _ = scored(grid, layer_at([(100, 100), (250, 250)]))
    assert result["object_detection_by_depth_threshold"][0]["labels_found"] == 0
    assert result["surface_agreement"]["by_depth_threshold"][0]["fraction"] == 0.0
    assert result["labels_missed_by_reason"] == {"NO_BASIN_WITHIN_MATCH_RADIUS": 2}


def test_the_positional_offset_is_honoured_and_reported_separately():
    grid = surface([(200, 200, 6.0, 8.0)])
    # The outline is drawn 25 m east of the basin: outside it, inside the offset.
    near = layer_at([(200, 232)], radius=5.0, positional_offset_m=40.0)
    result, _ = scored(grid, near)
    row = result["surface_agreement"]["by_depth_threshold"][0]
    assert row["fraction"] == 0.0 and row["fraction_within_positional_offset"] == 1.0
    assert result["object_detection_by_depth_threshold"][0]["labels_found"] == 1


def test_outlines_the_survey_does_not_cover_are_counted_not_scored():
    grid = surface([(100, 100, 6.0, 9.0)], nodata_block=(240, 320, 240, 320))
    layer = layer_at([(100, 100), (280, 280), (5, 5)])
    labels, counts = validation.labels_for_grid(layer, grid)
    assert [item.label_id for item in labels] == ["test_labels:1"]
    assert counts == {"in_set": 3, "outside_grid": 1, "not_covered": 1, "scored": 1}
    with pytest.raises(validation.ValidationError, match="not a label set"):
        validation.labels_for_grid(
            layer_at([(100, 100)], role=refsets.ReferenceRole.CONTEXT_AREA), grid
        )


def test_basins_the_method_does_not_stand_behind_are_left_out():
    grid = surface([(100, 100, 6.0, 9.0)])
    detections = detect(grid)
    flagged = [
        det.Detection(
            **{
                **{f: getattr(d, f) for f in d.__dataclass_fields__},
                "flags": (det.DetectionFlag.SEAM_OVERLAP,),
            }
        )
        for d in detections
    ]
    layer = layer_at([(100, 100)])
    labels, _ = validation.labels_for_grid(layer, grid)
    result = validation.score(
        flagged,
        labels,
        layer.ref,
        grid=grid,
        source_id="APSRC-" + "b" * 16,
        thresholds=[1],
        displaced_offset_m=150.0,
    )
    assert result["detections_excluded_as_possible_artifacts"] == len(detections)
    assert result["object_detection_by_depth_threshold"][0]["labels_found"] == 0
    # The surface is still read: the depression is there whoever reports it.
    assert result["surface_agreement"]["by_depth_threshold"][0]["fraction"] == 1.0


def test_the_window_is_chosen_by_rule():
    grid = surface([])
    cells = [(100, 100), (110, 110), (105, 95), (300, 300), (20, 20)]
    labels, _ = validation.labels_for_grid(
        layer_at(cells, radius=3.0, positional_offset_m=1.0), grid
    )
    bounds = (WEST, NORTH - 400, WEST + 400, NORTH)
    label_id, centre = validation.choose_window_centre(
        labels, bounds, half_size_m=60, cluster_radius_m=30
    )
    assert (
        label_id == "test_labels:1"
    )  # three neighbours; the tie goes to the smallest id
    assert (
        abs(centre[0] - (WEST + 100.5)) <= 1 and abs(centre[1] - (NORTH - 100.5)) <= 1
    )
    assert centre == (float(round(centre[0])), float(round(centre[1])))  # whole metres
    with pytest.raises(validation.ValidationError, match="far enough"):
        validation.choose_window_centre(
            labels, bounds, half_size_m=250, cluster_radius_m=30
        )


def test_a_validation_run_must_be_fully_declared(tmp_path):
    good = validation.load_validation_run(
        REPO / refsets.REFERENCE_PATH, "2026-11-17-karst-map"
    )
    assert good["depth_thresholds_m"] == [1, 2, 5, 10, 20, 30]
    data = yaml.safe_load((REPO / refsets.REFERENCE_PATH).read_text(encoding="utf-8"))
    for change, message in (
        ({"depth_thresholds_m": [5, 1]}, "increasing"),
        ({"tile_coarsen_factor": 1}, "at least 2"),
        ({"label_set": ""}, "name its label_set"),
        ({"cluster_radius_m": 0}, "positive number"),
    ):
        bad = json.loads(json.dumps(data))
        bad["validation_runs"][0].update(change)
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump(bad), encoding="utf-8")
        with pytest.raises(validation.ValidationError, match=message):
            validation.load_validation_run(path, "2026-11-17-karst-map")
    with pytest.raises(validation.ValidationError, match="no validation run"):
        validation.load_validation_run(REPO / refsets.REFERENCE_PATH, "missing")


# ── The committed reference sets and the committed comparison ────────────────


def test_committed_reference_sets_match_their_declared_bytes():
    sets = refsets.load_sets(REPO / refsets.REFERENCE_PATH)
    held = [s for s in sets.values() if s.held]
    assert {s.role for s in held} == {
        refsets.ReferenceRole.LABELS,
        refsets.ReferenceRole.CONTEXT_AREA,
        refsets.ReferenceRole.KARST_LIMIT,
    }
    for ref in held:
        layer = refsets.read_layer(ref, REPO)
        assert layer.features and layer.dropped_empty == 0
    labels = refsets.read_layer(sets["usgs_karst_sinkholes_over_30m"], REPO)
    assert labels.read == 1173 and labels.file_declares_crs is False
    assert (
        labels.ref.bound_crs == "EPSG:32161" and labels.ref.positional_offset_m == 100
    )
    # The coherence the binding rests on: the outlines fall inside the karst limit.
    limit = refsets.read_layer(sets["pr_planning_board_northern_karst_limit"], REPO)
    boundary = refsets.reproject(limit.features[0].geometry, "EPSG:6566", "EPSG:32161")
    inside = sum(1 for f in labels.features if boundary.contains(f.geometry.centroid))
    assert inside >= 1170
    for ref in sets.values():
        if not ref.held:
            assert ref.format is refsets.ReferenceFormat.OPAQUE and ref.path is None


@pytest.fixture(scope="module")
def committed():
    report = validation.current_report(REPO)
    if report is None:
        pytest.skip("no validation run is committed")
    return report


def test_the_committed_comparison_is_reproduced_and_claims_no_field_accuracy(committed):
    run = validation.load_validation_run(
        REPO / refsets.REFERENCE_PATH, committed["run_id"]
    )
    assert validation.check_report(run, repo_root=REPO) == []
    assert committed["registry_changes"] == 0
    assert committed["method"]["thresholds_changed_by_this_run"] is False
    sections = [committed["window"], *committed["whole_tile"]["epochs"].values()]
    for section in sections:
        assert section["evaluation_state"] == "REFERENCE_COMPARED"
        assert section["precision"] is None
        for row in section["surface_agreement"]["by_depth_threshold"]:
            assert row["outlines_on_a_depression"] <= row["outlines"]
            assert row["displaced_on_a_depression"] <= row["displaced_outlines"]
        counts = section["label_counts"]
        assert (
            counts["scored"] + counts["outside_grid"] + counts["not_covered"]
            == counts["in_set"]
        )
    assert any("not a field survey" in limit for limit in committed["limits"])
    context = committed["context_for_the_survey_run"]
    assert context["record"] == "INAP-PR-000003"
    assert context["mapped_sinkholes_over_30m_in_the_survey_window"] == 0


def test_reference_maps_are_registered_and_change_no_record(committed):
    build = seeding.build_all(REPO)
    assert build.reference["registered"] == 3
    sets = refsets.load_sets(REPO / refsets.REFERENCE_PATH)
    held_ids = {refsets.to_source(s).source_id for s in sets.values() if s.held}
    assert held_ids <= set(build.inland.sources)
    for source_id in held_ids:
        source = build.inland.sources[source_id]
        assert source.provenance_state is v.ProvenanceState.REGISTERED
        assert not source.is_direct_measurement
    cited = {
        sid
        for f in build.inland.features.values()
        for a in f.assertions
        for sid in a.source_ids
    }
    assert not cited & held_ids
    statuses = build.inland.counts()["features_by_status"]
    assert statuses["CANDIDATE"] == 4 and statuses["VERIFIED"] == 0


def test_a_changed_label_file_stops_the_comparison(committed, tmp_path):
    crosswalk = yaml.safe_load(
        (REPO / seeding.CROSSWALK_PATH).read_text(encoding="utf-8")
    )
    for rel in (
        refsets.REFERENCE_PATH,
        survey_run.RUNS_PATH,
        "registry/access_points/inland.json",
        str(crosswalk["legacy_file"]),
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    for rel in (
        "evidence/access_points/reference",
        f"{validation.VALIDATION_DIR}/{committed['run_id']}",
        f"{survey_run.SURVEY_DIR}/{committed['survey_run']}",
    ):
        shutil.copytree(REPO / rel, tmp_path / rel)
    run = validation.load_validation_run(
        tmp_path / refsets.REFERENCE_PATH, committed["run_id"]
    )
    assert validation.check_report(run, repo_root=tmp_path) == []
    labels = (
        tmp_path
        / "evidence/access_points/reference/usgs_karst_map/sinkholes_30m.geojson"
    )
    labels.write_bytes(labels.read_bytes().replace(b'">30m"', b'">31m"', 1))
    problems = validation.check_report(run, repo_root=tmp_path)
    assert problems and "declared hash" in problems[0]
