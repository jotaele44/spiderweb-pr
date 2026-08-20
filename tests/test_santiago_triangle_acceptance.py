from __future__ import annotations

import csv
import json
from pathlib import Path
import zipfile

import pytest
from shapely.geometry import LineString, Point

from spiderweb.subsurface.acceptance import (
    build_acceptance_snapshot,
    compare_acceptance_snapshots,
)
from spiderweb.subsurface.aoi import freeze_aoi
from spiderweb.subsurface.artifacts import (
    export_csv,
    export_geojson,
    export_kml,
    export_kmz,
)
from spiderweb.subsurface.dispatcher import LAYER_FAMILIES, SubsurfaceDispatcher
from spiderweb.subsurface.evidence import EvidenceTier, SpatialState, adjudicate_feature


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "subsurface"
SANTIAGO_KML = FIXTURE_DIR / "santiago_triangle.kml"
FREEZE_RECEIPT = FIXTURE_DIR / "santiago_triangle.freeze.json"
BASELINE = FIXTURE_DIR / "santiago_triangle.baseline.json"
CANONICAL_SHA256 = "4b4109c31681f8d510b8dba9ca0a9018d165ab88ecc05a0625c8a98ce3aca3c8"
SOURCE_SHA256 = "c8bf698be741bcd439228901cfd3f9304b86a73c8a968c5f7c9f2343d36de34f"


def _fixture_record(aoi, record_id: str, geometry):
    return adjudicate_feature(
        aoi=aoi,
        record_id=record_id,
        source_id="SYNTHETIC_SPATIAL_STATE_FIXTURE",
        layer_family="GEOLOGY_KARST_CAVES",
        source_uri="fixture://santiago-triangle/spatial-states",
        source_sha256="fixture-not-authoritative",
        retrieved_utc="2026-08-20T18:12:00Z",
        feature=geometry,
        asserted_tier=EvidenceTier.CANDIDATE,
        basis=["synthetic_regression_fixture"],
        attributes={"fixture_only": True},
    )


def test_santiago_triangle_frozen_identity_matches_receipt():
    receipt = json.loads(FREEZE_RECEIPT.read_text(encoding="utf-8"))
    frozen = freeze_aoi(SANTIAGO_KML)
    assert frozen.source_sha256 == receipt["source_sha256"] == SOURCE_SHA256
    assert frozen.canonical_sha256 == receipt["canonical_sha256"] == CANONICAL_SHA256
    assert frozen.source_crs == receipt["source_crs"] == "OGC:CRS84"
    assert frozen.source_feature_count == 1
    assert frozen.source_has_z is True
    assert frozen.analysis_dimension_loss == ("Z",)
    assert list(frozen.geometry.bounds) == receipt["bounds"]


def test_current_authoritative_adapter_denominator_executes_without_false_negative():
    frozen = freeze_aoi(SANTIAGO_KML)
    dispatcher = SubsurfaceDispatcher()
    plan = dispatcher.plan()
    outputs = dispatcher.run(frozen)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert outputs == {}
    assert {task.family for task in plan} == set(LAYER_FAMILIES)
    assert all(task.state == "OPEN" for task in plan)
    assert baseline["record_count"] == 0
    assert baseline["certification"] == "OPEN"
    assert "not zero subsurface evidence" in baseline["interpretation"]


def test_santiago_triangle_exercises_all_four_terminal_spatial_states():
    aoi = freeze_aoi(SANTIAGO_KML).geometry
    minx, miny, maxx, maxy = aoi.bounds
    states = {
        "within": _fixture_record(aoi, "within", aoi.representative_point()).spatial_state,
        "partial": _fixture_record(
            aoi,
            "partial",
            LineString([(minx - 0.1, (miny + maxy) / 2), (maxx + 0.1, (miny + maxy) / 2)]),
        ).spatial_state,
        "touch": _fixture_record(aoi, "touch", Point(aoi.exterior.coords[0])).spatial_state,
        "outside": _fixture_record(aoi, "outside", Point(minx - 1, maxy + 1)).spatial_state,
    }
    assert states == {
        "within": SpatialState.FULLY_WITHIN,
        "partial": SpatialState.PARTIAL,
        "touch": SpatialState.TOUCH_ONLY,
        "outside": SpatialState.OUTSIDE,
    }


def test_acceptance_exports_and_source_manifest_preserve_complete_fixture_set(tmp_path: Path):
    frozen = freeze_aoi(SANTIAGO_KML)
    aoi = frozen.geometry
    minx, miny, maxx, maxy = aoi.bounds
    records = [
        _fixture_record(aoi, "within", aoi.representative_point()),
        _fixture_record(
            aoi,
            "partial",
            LineString([(minx - 0.1, (miny + maxy) / 2), (maxx + 0.1, (miny + maxy) / 2)]),
        ),
        _fixture_record(aoi, "touch", Point(aoi.exterior.coords[0])),
        _fixture_record(aoi, "outside", Point(minx - 1, maxy + 1)),
    ]
    records_by_family = {"GEOLOGY_KARST_CAVES": records}
    snapshot = build_acceptance_snapshot(
        aoi_canonical_sha256=frozen.canonical_sha256,
        dispatch_plan=SubsurfaceDispatcher().plan(),
        records_by_family=records_by_family,
    )
    source = snapshot["sources"]["GEOLOGY_KARST_CAVES|SYNTHETIC_SPATIAL_STATE_FIXTURE"]
    assert source["record_count"] == 4
    assert source["record_ids"] == ["outside", "partial", "touch", "within"]
    assert snapshot["record_count"] == 4

    csv_path = export_csv(tmp_path / "evidence.csv", records)
    geojson_path = export_geojson(tmp_path / "evidence.geojson", records)
    kml_path = export_kml(tmp_path / "evidence.kml", records)
    kmz_path = export_kmz(tmp_path / "evidence.kmz", records)

    with csv_path.open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 4
    assert len(json.loads(geojson_path.read_text(encoding="utf-8"))["features"]) == 4
    kml_text = kml_path.read_text(encoding="utf-8")
    assert all(record.record_id in kml_text for record in records)
    with zipfile.ZipFile(kmz_path) as zf:
        assert zf.namelist() == ["doc.kml"]
        assert zf.read("doc.kml").startswith(b"<?xml")


def test_new_adapter_additions_are_monotonic_and_visible():
    frozen = freeze_aoi(SANTIAGO_KML)
    baseline = build_acceptance_snapshot(
        aoi_canonical_sha256=frozen.canonical_sha256,
        dispatch_plan=SubsurfaceDispatcher().plan(),
        records_by_family={},
    )

    dispatcher = SubsurfaceDispatcher()

    def adapter(aoi_receipt):
        return [_fixture_record(aoi_receipt.geometry, "adapter-r1", aoi_receipt.geometry.representative_point())]

    dispatcher.register("GEOLOGY_KARST_CAVES", adapter, name="acceptance_fixture_adapter")
    outputs = dispatcher.run(frozen)
    current = build_acceptance_snapshot(
        aoi_canonical_sha256=frozen.canonical_sha256,
        dispatch_plan=dispatcher.plan(),
        records_by_family=outputs,
    )
    diff = compare_acceptance_snapshots(baseline, current)
    assert diff.added == (
        "GEOLOGY_KARST_CAVES|SYNTHETIC_SPATIAL_STATE_FIXTURE|adapter-r1",
    )
    assert diff.removed == ()


def test_prior_candidate_disappearance_fails_closed():
    frozen = freeze_aoi(SANTIAGO_KML)
    record = _fixture_record(frozen.geometry, "must-survive", frozen.geometry.representative_point())
    previous = build_acceptance_snapshot(
        aoi_canonical_sha256=frozen.canonical_sha256,
        dispatch_plan=SubsurfaceDispatcher().plan(),
        records_by_family={"GEOLOGY_KARST_CAVES": [record]},
    )
    current = build_acceptance_snapshot(
        aoi_canonical_sha256=frozen.canonical_sha256,
        dispatch_plan=SubsurfaceDispatcher().plan(),
        records_by_family={},
    )
    with pytest.raises(AssertionError, match="prior records disappeared"):
        compare_acceptance_snapshots(previous, current)


def test_acceptance_fixture_cannot_drift_to_a_new_aoi_silently():
    previous = {"aoi_canonical_sha256": CANONICAL_SHA256, "records": {}}
    current = {"aoi_canonical_sha256": "different", "records": {}}
    with pytest.raises(ValueError, match="new fixture lineage"):
        compare_acceptance_snapshots(previous, current)
