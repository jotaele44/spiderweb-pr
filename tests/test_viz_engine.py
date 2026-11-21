"""Geospatial Visualization Engine: contract, determinism and receipt tests."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from federation.spatial_core import canonical_json_sha256  # noqa: E402
from viz_engine import cli  # noqa: E402
from viz_engine.engine import export_publication, render, verify_artifact  # noqa: E402
from viz_engine.snapshot import load_snapshot  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "viz"
SNAP = FIX / "pilot_snapshot"
SCHEMAS = Path(__file__).parent.parent / "schemas"
VIEWS = {"xy": "svg", "section": "svg", "3d": "gltf"}


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _config(view: str) -> dict:
    return json.loads((FIX / "configs" / f"{view}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("view", VIEWS)
def test_pilot_renders_and_passes(tmp_path, view):
    res = render(SNAP, view, _config(view), tmp_path)
    assert res.status == "PASS"
    assert res.receipt["publication_ready"] is True
    assert res.artifact.suffix == "." + VIEWS[view]


@pytest.mark.parametrize("view", VIEWS)
def test_render_is_byte_reproducible(tmp_path, view):
    a = render(SNAP, view, _config(view), tmp_path / "a")
    b = render(SNAP, view, _config(view), tmp_path / "b")
    assert a.artifact.read_bytes() == b.artifact.read_bytes()
    assert a.receipt_path.read_bytes() == b.receipt_path.read_bytes()
    assert (
        a.receipt["output"]["sha256"]
        == hashlib.sha256(a.artifact.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("view", VIEWS)
def test_receipt_matches_schema_and_hash(tmp_path, view):
    res = render(SNAP, view, _config(view), tmp_path)
    jsonschema.validate(res.receipt, _schema("viz_receipt_v1.schema.json"))
    body = {k: v for k, v in res.receipt.items() if k != "receipt_sha256"}
    assert res.receipt["receipt_sha256"] == canonical_json_sha256(body)
    assert verify_artifact(res.artifact, res.receipt_path)


def test_tampered_artifact_fails_verification(tmp_path):
    res = render(SNAP, "xy", _config("xy"), tmp_path)
    res.artifact.write_text(res.artifact.read_text() + "<!-- edited -->")
    assert not verify_artifact(res.artifact, res.receipt_path)


def test_receipt_records_inputs_frame_and_evidence(tmp_path):
    r = render(SNAP, "xy", _config("xy"), tmp_path).receipt
    manifest = load_snapshot(SNAP).manifest
    assert {x["sha256"] for x in r["inputs"]["layers"]} == {
        e["sha256"] for e in manifest["layers"]
    }
    assert r["reference_frame"]["crs"] == "EPSG:4326"
    assert r["reference_frame"]["vertical_datum"] == "NAVD88"
    assert r["observation_dates"] == ["2025-03-01"]
    assert set(r["evidence_counts"]) == {"observed", "inferred", "modeled", "unknown"}
    assert (
        r["evidence_counts"]["unknown"] == 1 and r["evidence_counts"]["inferred"] == 1
    )


def test_snapshot_and_scene_schemas_accept_fixtures():
    jsonschema.validate(
        json.loads((SNAP / "snapshot.json").read_text()),
        _schema("viz_snapshot_v1.schema.json"),
    )
    for view in VIEWS:
        jsonschema.validate(_config(view), _schema("viz_scene_v1.schema.json"))


def test_evidence_classes_drive_link_styling(tmp_path):
    res = render(SNAP, "xy", _config("xy"), tmp_path)
    svg = res.artifact.read_text()
    styles = {f["id"]: f["style"] for f in res.receipt["features"]}
    assert styles["C_OBS"] == "link" and styles["C_INF"] == "link"
    assert styles["C_UNK"] == "not_drawn"
    assert (
        'stroke="#c77700" stroke-width="2.00" stroke-dasharray="3 4"' in svg
    )  # inferred is dashed
    assert "a drawn line is not evidence" in svg


def test_unknown_link_is_never_drawn_in_section_or_3d(tmp_path):
    for view in ("section", "3d"):
        feats = {
            f["id"]: f["style"]
            for f in render(SNAP, view, _config(view), tmp_path / view).receipt[
                "features"
            ]
        }
        assert feats["C_UNK"] == "not_drawn"
        assert feats["C_OBS"] == "link"


def test_date_selection_filters_observations(tmp_path):
    cfg = {**_config("xy"), "date": "2024-01-01"}
    r = render(SNAP, "xy", cfg, tmp_path).receipt
    assert not [f for f in r["features"] if f["layer_id"] == "wells_fixture"]


def test_section_vertical_exaggeration_is_recorded_and_applied(tmp_path):
    lo = render(
        SNAP,
        "section",
        {**_config("section"), "vertical_exaggeration": 4},
        tmp_path / "lo",
    )
    hi = render(
        SNAP,
        "section",
        {**_config("section"), "vertical_exaggeration": 12},
        tmp_path / "hi",
    )
    assert any("vertical exaggeration 4x" in s for s in lo.receipt["processing_steps"])
    assert any("vertical exaggeration 12x" in s for s in hi.receipt["processing_steps"])
    assert lo.artifact.read_bytes() != hi.artifact.read_bytes()


def test_gltf_is_self_consistent(tmp_path):
    res = render(SNAP, "3d", _config("3d"), tmp_path)
    doc = json.loads(res.artifact.read_text())
    assert doc["asset"]["version"] == "2.0"
    assert doc["asset"]["extras"]["validation_status"] == "PASS"
    blob = base64.b64decode(doc["buffers"][0]["uri"].split(",", 1)[1])
    assert len(blob) == doc["buffers"][0]["byteLength"]
    assert max(v["byteOffset"] + v["byteLength"] for v in doc["bufferViews"]) == len(
        blob
    )


def test_3d_pilot_is_bounded(tmp_path, monkeypatch):
    import viz_engine.render_3d as r3

    monkeypatch.setattr(r3, "MAX_CELLS", 10)
    with pytest.raises(ValueError, match="bounded"):
        render(SNAP, "3d", _config("3d"), tmp_path)


def test_cli_render_and_verify(tmp_path, capsys):
    cfg = FIX / "configs" / "xy.json"
    assert (
        cli.main(
            [
                "render",
                "--view",
                "xy",
                "--snapshot",
                str(SNAP),
                "--config",
                str(cfg),
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    art = tmp_path / "pilot_fixture_xy.svg"
    assert (
        cli.main(
            ["verify", "--artifact", str(art), "--receipt", str(art) + ".receipt.json"]
        )
        == 0
    )
    assert "OK" in capsys.readouterr().out


def test_publication_export_copies_artifact_and_receipt(tmp_path):
    res = render(SNAP, "xy", _config("xy"), tmp_path / "r")
    out = export_publication(res, tmp_path / "pub")
    assert out.exists() and (tmp_path / "pub" / (out.name + ".receipt.json")).exists()


def _copy_snapshot(tmp_path: Path) -> Path:
    dest = tmp_path / "snap"
    shutil.copytree(SNAP, dest)
    return dest


def test_originals_are_not_modified_by_rendering(tmp_path):
    before = {p: p.read_bytes() for p in SNAP.rglob("*") if p.is_file()}
    for view in VIEWS:
        render(SNAP, view, _config(view), tmp_path / view)
    assert before == {p: p.read_bytes() for p in SNAP.rglob("*") if p.is_file()}


def test_manifest_copy_is_deepcopy_safe():
    m = load_snapshot(SNAP).manifest
    assert copy.deepcopy(m) == m
