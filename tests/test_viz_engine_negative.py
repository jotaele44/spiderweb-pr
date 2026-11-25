"""Negative gates: a convincing picture must never stand in for evidence."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from viz_engine import cli
from viz_engine.engine import PublicationBlocked, export_publication, render
from viz_engine.snapshot import SnapshotIntegrityError, freeze_snapshot, load_snapshot

FIX = Path(__file__).parent / "fixtures" / "viz"
SNAP = FIX / "pilot_snapshot"


def cfg(view: str) -> dict:
    return json.loads((FIX / "configs" / f"{view}.json").read_text(encoding="utf-8"))


@pytest.fixture
def snap(tmp_path) -> Path:
    dest = tmp_path / "snap"
    shutil.copytree(SNAP, dest)
    return dest


def edit(snap: Path, layer: str, fn) -> None:
    """Mutate a layer file, then re-pin it (a legitimate new snapshot, bad content)."""
    path = snap / "layers" / layer
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    m = load_manifest(snap)
    freeze_snapshot(
        snap,
        snapshot_id=m["snapshot_id"],
        version=m["version"],
        crs=m["crs"],
        vertical_datum=m["vertical_datum"],
        extent=m["extent"],
    )


def load_manifest(snap: Path) -> dict:
    return json.loads((snap / "snapshot.json").read_text())


def feat(data: dict, fid: str) -> dict:
    return next(f for f in data["features"] if f["id"] == fid)


def codes(res) -> set[str]:
    return {
        i["code"]
        for i in res.receipt["validation"]["issues"]
        if i["severity"] == "error"
    }


def assert_blocked(res, code: str) -> None:
    assert res.status == "FAIL" and code in codes(res)
    assert res.receipt["publication_ready"] is False
    assert (
        "VALIDATION FAILED - NOT FOR PUBLICATION" in res.artifact.read_text()
        or res.artifact.suffix == ".gltf"
    )
    with pytest.raises(PublicationBlocked):
        export_publication(res, res.artifact.parent / "pub")


def test_reversed_river_flow(snap, tmp_path):
    def flip(d):
        g = feat(d, "SEG_3")["geometry"]["coordinates"]
        g.reverse()

    edit(snap, "hydro.json", flip)
    assert_blocked(render(snap, "xy", cfg("xy"), tmp_path), "REVERSED_FLOW")


def test_mismatched_vertical_datum(snap, tmp_path):
    edit(snap, "dem.json", lambda d: d.update(vertical_datum="MSL"))
    assert_blocked(render(snap, "section", cfg("section"), tmp_path), "DATUM_MISMATCH")


def test_mismatched_crs(snap, tmp_path):
    edit(snap, "wells.json", lambda d: d.update(crs="EPSG:32161"))
    assert_blocked(render(snap, "xy", cfg("xy"), tmp_path), "CRS_MISMATCH")


def test_mismatched_vertical_unit(snap, tmp_path):
    edit(snap, "dem.json", lambda d: d.update(unit="ft"))
    assert_blocked(render(snap, "3d", cfg("3d"), tmp_path), "UNIT_MISMATCH")


def test_disconnected_network_segment(snap, tmp_path):
    def add(d):
        d["features"].append(
            {
                "id": "SEG_X",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-66.19, 18.19], [-66.18, 18.18]],
                },
                "properties": {
                    "from_node": "X1",
                    "to_node": "X2",
                    "evidence": "observed",
                    "flow_direction": "digitized_downstream",
                },
            }
        )

    edit(snap, "hydro.json", add)
    assert_blocked(render(snap, "xy", cfg("xy"), tmp_path), "DISCONNECTED_SEGMENT")


def test_declared_isolated_segment_is_allowed(snap, tmp_path):
    def add(d):
        d["features"].append(
            {
                "id": "SEG_X",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-66.19, 18.19], [-66.18, 18.18]],
                },
                "properties": {
                    "from_node": "X1",
                    "to_node": "X2",
                    "evidence": "observed",
                    "network_role": "isolated_declared",
                },
            }
        )

    edit(snap, "hydro.json", add)
    assert render(snap, "xy", cfg("xy"), tmp_path).status == "PASS"


def test_missing_raster_coverage_for_map_extent(snap, tmp_path):
    config = {**cfg("xy"), "extent": [-66.3, 18.0, -66.0, 18.2]}
    assert_blocked(render(snap, "xy", config, tmp_path), "MISSING_RASTER_COVERAGE")


def test_missing_raster_coverage_for_transect(snap, tmp_path):
    config = {**cfg("section"), "transect": [[-66.1, 18.19], [-66.1, 18.3]]}
    assert_blocked(render(snap, "section", config, tmp_path), "MISSING_RASTER_COVERAGE")


def test_nodata_cells_count_as_missing_coverage(snap, tmp_path):
    def hole(d):
        for r in range(len(d["values"])):
            for c in range(len(d["values"][r])):
                if 5 <= r <= 8 and 5 <= c <= 8:
                    d["values"][r][c] = d["nodata"]

    edit(snap, "dem.json", hole)
    assert_blocked(
        render(snap, "section", cfg("section"), tmp_path), "MISSING_RASTER_COVERAGE"
    )


def test_no_raster_layer_blocks_section(snap, tmp_path):
    (snap / "layers" / "dem.json").unlink()
    m = load_manifest(snap)
    freeze_snapshot(
        snap,
        snapshot_id=m["snapshot_id"],
        version=m["version"],
        crs=m["crs"],
        vertical_datum=m["vertical_datum"],
        extent=m["extent"],
    )
    assert_blocked(render(snap, "section", cfg("section"), tmp_path), "NO_RASTER")


def test_observed_connection_requires_observation_ref(snap, tmp_path):
    edit(
        snap,
        "connections.json",
        lambda d: feat(d, "C_OBS")["properties"].pop("observation_ref"),
    )
    assert_blocked(render(snap, "xy", cfg("xy"), tmp_path), "UNSUPPORTED_CONNECTION")


def test_modeled_connection_requires_model_id(snap, tmp_path):
    edit(
        snap,
        "connections.json",
        lambda d: feat(d, "C_INF")["properties"].update(evidence="modeled"),
    )
    assert_blocked(render(snap, "xy", cfg("xy"), tmp_path), "UNSUPPORTED_CONNECTION")


def test_modeled_connection_with_model_id_is_drawn_dashed(snap, tmp_path):
    edit(
        snap,
        "connections.json",
        lambda d: feat(d, "C_INF")["properties"].update(
            evidence="modeled", model_id="fixture-model-1"
        ),
    )
    res = render(snap, "xy", cfg("xy"), tmp_path)
    assert res.status == "PASS" and 'stroke-dasharray="8 3"' in res.artifact.read_text()


def test_connection_to_nonexistent_feature(snap, tmp_path):
    edit(
        snap,
        "connections.json",
        lambda d: feat(d, "C_INF")["properties"].update(to_id="GHOST_9"),
    )
    assert_blocked(
        render(snap, "xy", cfg("xy"), tmp_path), "CONNECTION_ENDPOINT_MISSING"
    )


def test_missing_or_bogus_evidence_is_unknown_and_not_drawn(snap, tmp_path):
    edit(
        snap,
        "connections.json",
        lambda d: feat(d, "C_INF")["properties"].update(evidence="very_likely"),
    )
    res = render(snap, "xy", cfg("xy"), tmp_path)
    styles = {f["id"]: (f["evidence"], f["style"]) for f in res.receipt["features"]}
    assert styles["C_INF"] == ("unknown", "not_drawn")
    assert any(
        i["code"] == "UNKNOWN_EVIDENCE_CLASS" and i["severity"] == "warning"
        for i in res.receipt["validation"]["issues"]
    )


def test_duplicate_feature_ids_across_layers(snap, tmp_path):
    edit(snap, "wells.json", lambda d: feat(d, "W3").update(id="SEG_1"))
    assert_blocked(render(snap, "xy", cfg("xy"), tmp_path), "DUPLICATE_FEATURE_ID")


def test_merged_feature_without_adjudication(snap, tmp_path):
    edit(
        snap,
        "wells.json",
        lambda d: feat(d, "W3")["properties"].update(merged_from=["W3_A", "W3_B"]),
    )
    assert_blocked(
        render(snap, "xy", cfg("xy"), tmp_path), "MERGED_ID_WITHOUT_ADJUDICATION"
    )


def test_merged_feature_with_adjudication_is_allowed(snap, tmp_path):
    edit(
        snap,
        "wells.json",
        lambda d: feat(d, "W3")["properties"].update(
            merged_from=["W3_A"], identity_adjudication="case-001"
        ),
    )
    assert render(snap, "xy", cfg("xy"), tmp_path).status == "PASS"


def test_unsupported_well_depth_reference(snap, tmp_path):
    edit(
        snap,
        "wells.json",
        lambda d: feat(d, "W1")["properties"].update(depth_reference="above_sea_level"),
    )
    assert_blocked(
        render(snap, "section", cfg("section"), tmp_path), "DEPTH_REFERENCE_UNSUPPORTED"
    )


def test_changed_input_bytes_are_rejected_before_rendering(snap, tmp_path):
    path = snap / "layers" / "wells.json"
    path.write_text(path.read_text().replace("150.0", "1500.0"))  # not re-pinned
    with pytest.raises(SnapshotIntegrityError):
        render(snap, "xy", cfg("xy"), tmp_path)
    with pytest.raises(SnapshotIntegrityError):
        load_snapshot(snap)


def test_excessive_vertical_exaggeration_is_refused_not_clamped(snap, tmp_path):
    with pytest.raises(ValueError, match="vertical exaggeration"):
        render(
            snap, "section", {**cfg("section"), "vertical_exaggeration": 50}, tmp_path
        )


def test_unknown_view_rejected(snap, tmp_path):
    with pytest.raises(ValueError, match="unknown view"):
        render(snap, "isometric", {}, tmp_path)


def test_cli_exit_code_signals_failed_validation(snap, tmp_path):
    edit(snap, "dem.json", lambda d: d.update(vertical_datum="MSL"))
    code = cli.main(
        [
            "render",
            "--view",
            "xy",
            "--snapshot",
            str(snap),
            "--config",
            str(FIX / "configs" / "xy.json"),
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 3


def test_failed_render_changes_render_id_inputs_not_receipt_integrity(snap, tmp_path):
    ok = render(SNAP, "xy", cfg("xy"), tmp_path / "ok")
    edit(
        snap,
        "hydro.json",
        lambda d: feat(d, "SEG_3")["geometry"]["coordinates"].reverse(),
    )
    bad = render(snap, "xy", cfg("xy"), tmp_path / "bad")
    assert ok.receipt["render_id"] != bad.receipt["render_id"]
    assert bad.receipt["receipt_sha256"] != ok.receipt["receipt_sha256"]
