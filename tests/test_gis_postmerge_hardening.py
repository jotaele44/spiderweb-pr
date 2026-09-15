"""Synthetic negative/positive gates; no PR layer measurements or identity claims."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import json

import pytest

from spiderweb.spatial.archipelago import (
    GeometryDerivationState as D, GeometryManifestation as G,
    GeometryOrigin as O, GeometryRepresentation as R,
)
from spiderweb.spatial.lineage_validation import validate_manifestation_dag
from tools.gis_evidence.core import canonical_json, digest
from tools.gis_evidence.lineage_admission import admit_source_lineage
from tools.gis_evidence.viewport_parity import compare_rendered_trials
from tools.gis_evidence.delivery_benchmark import preflight


def node(key, parent=None, state=D.SOURCE_NATIVE):
    return G(key, "SYNTHETIC_ONLY", R.POLYGON,
             O.SOURCE_NATIVE if state == D.SOURCE_NATIVE else O.DERIVED,
             "Polygon", parent_manifestation_id=parent, derivation_state=state)


@pytest.mark.parametrize("parent_state", [D.SIMPLIFIED, D.DELIVERY_MINIMIZED])
@pytest.mark.parametrize("child_state", [D.FULL, D.CANONICALIZED_FULL])
def test_lossy_to_full_rejected(parent_state, child_state):
    with pytest.raises(ValueError, match="LOSSY_AUTHORITY_REVERSAL"):
        validate_manifestation_dag([
            node("s"), node("p", "s", parent_state), node("c", "p", child_state)])


def test_intermediate_delivery_label_cannot_launder_loss():
    with pytest.raises(ValueError, match="LOSSY_AUTHORITY_REVERSAL"):
        validate_manifestation_dag([
            node("s"), node("p", "s", D.SIMPLIFIED),
            node("d", "p", D.DELIVERY_MINIMIZED), node("c", "d", D.FULL)])


@pytest.mark.parametrize("parent_state", [D.SOURCE_NATIVE, D.FULL, D.CANONICALIZED_FULL])
@pytest.mark.parametrize("child_state", [D.FULL, D.CANONICALIZED_FULL, D.SIMPLIFIED,
                                         D.DELIVERY_MINIMIZED, D.MVT])
def test_full_or_native_allows_forward_derivation(parent_state, child_state):
    rows = [node("s")]
    parent = "s"
    if parent_state != D.SOURCE_NATIVE:
        rows.append(node("p", "s", parent_state)); parent = "p"
    rows.append(node("c", parent, child_state))
    assert validate_manifestation_dag(rows).canonical_identity_certified is False


@pytest.mark.parametrize("parent_state", [D.SIMPLIFIED, D.DELIVERY_MINIMIZED])
@pytest.mark.parametrize("child_state", [D.SIMPLIFIED, D.DELIVERY_MINIMIZED, D.MVT])
def test_lossy_remains_lossy(parent_state, child_state):
    assert validate_manifestation_dag([
        node("s"), node("p", "s", parent_state),
        node("c", "p", child_state)]).state == "PASS_STRUCTURAL_ONLY"


def make_lock(tmp_path, rows=None, selected="s"):
    source_hash = digest(b"frozen synthetic source")
    path = tmp_path / "lineage.json"
    obj = {"schema": "spiderweb.geometry-lineage-lock.v1",
           "nodes": [asdict(r) for r in (rows or [node("s")])],
           "artifact_bindings": [{"geometry_manifestation_id": selected,
               "artifact_sha256": source_hash, "source_snapshot_id": "TEST_SNAPSHOT"}]}
    path.write_bytes(canonical_json(obj))
    spec = {"lineage_lock": {"path": str(path), "sha256": digest(path.read_bytes())},
            "manifestation_id": selected, "source_sha256": source_hash,
            "source_snapshot_id": "TEST_SNAPSHOT"}
    return path, obj, spec


def test_lineage_admission_positive_and_serialization(tmp_path):
    _, _, spec = make_lock(tmp_path)
    receipt = admit_source_lineage(spec)
    assert receipt["state"] == "PASS_STRUCTURAL_ARTIFACT_BINDING"
    assert receipt["canonical_identity_certified"] is False
    assert receipt["source_claims_independently_verified"] is False
    # Existing wire enum strings are accepted without inventing missing lineage.
    legacy = G("old", "TEST", R.POINT, O.SOURCE_NATIVE, "Point")
    restored = G(**json.loads(json.dumps(asdict(legacy))))
    assert restored.parent_manifestation_id is None
    with pytest.raises(ValueError, match="UNRESOLVED_LINEAGE"):
        validate_manifestation_dag([restored])


@pytest.mark.parametrize("field,error", [("source_sha256", "HASH_MISMATCH"),
    ("source_snapshot_id", "SNAPSHOT_MISMATCH"), ("manifestation_id", "NOT_BOUND")])
def test_lock_must_bind_selected_artifact(tmp_path, field, error):
    _, _, spec = make_lock(tmp_path)
    spec[field] = "0" * 64
    with pytest.raises(ValueError, match=error):
        admit_source_lineage(spec)


def test_lossy_lineage_fails_consumer_preflight(tmp_path):
    _, _, spec = make_lock(tmp_path, [node("s"), node("l", "s", D.SIMPLIFIED),
        node("fake_full", "l", D.FULL)], selected="fake_full")
    result = preflight({"layer_id": "synthetic", **spec})
    assert result["state"] == "BLOCKED"
    assert any("LOSSY_AUTHORITY_REVERSAL" in error for error in result["issues"])


def test_mutating_frozen_lock_fails_hash(tmp_path):
    path, _, spec = make_lock(tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        admit_source_lineage(spec)


def test_mvt_rejected_as_geojson_authority(tmp_path):
    _, _, spec = make_lock(tmp_path, [node("s"), node("tile", "s", D.MVT)], "tile")
    with pytest.raises(ValueError, match="MVT_CANNOT_BE_CANONICAL"):
        admit_source_lineage(spec)


def test_duplicate_json_fields_do_not_silently_override(tmp_path):
    path, _, spec = make_lock(tmp_path)
    path.write_text('{"schema":"a","schema":"b"}')
    spec["lineage_lock"]["sha256"] = digest(path.read_bytes())
    with pytest.raises(ValueError, match="DUPLICATE_JSON_FIELD"):
        admit_source_lineage(spec)


def test_duplicate_binding_fails(tmp_path):
    path, obj, spec = make_lock(tmp_path)
    obj["artifact_bindings"].append(deepcopy(obj["artifact_bindings"][0]))
    path.write_bytes(canonical_json(obj))
    spec["lineage_lock"]["sha256"] = digest(path.read_bytes())
    with pytest.raises(ValueError, match="DUPLICATE_LINEAGE_ARTIFACT_BINDING"):
        admit_source_lineage(spec)


def parity_fixture():
    spec = {"repetitions": 1, "viewports": [{"id": "v", "center": [-66.4, 18.22],
        "zoom": 9, "pan_path": [[-66.25, 18.28]], "expect_nonempty": True}]}
    snapshots = [
        {"step_id": "initial", "visible_ids": ["a", "b"], "rendered_fragment_count": 3,
         "camera": {"center": [-66.4,18.22], "zoom":9, "pitch":0, "bearing":0,
                    "canvas_pixels": [1280,800]}},
        {"step_id": "pan:0", "visible_ids": ["b"], "rendered_fragment_count": 2,
         "camera": {"center": [-66.25,18.28], "zoom":9, "pitch":0, "bearing":0,
                    "canvas_pixels": [1280,800]}},
    ]
    trials = [{"viewport_id": "v", "repetition": 0, "mode": mode,
               "measurement": {"viewport_snapshots": deepcopy(snapshots)}}
              for mode in ("geojson", "mvt")]
    return spec, trials


def test_paired_checkpoints_pass_and_keep_all_set_receipts():
    spec, trials = parity_fixture()
    result = compare_rendered_trials(trials,spec,{"a","b","c"})
    assert result["state"] == "PASS_RENDERED_ID_PARITY"
    assert result["paired_checkpoint_count"] == 2
    assert result["records"][0]["sets"]["counts"] == {
        "intersection":2,"a_only":0,"b_only":0,"union":2,"symmetric_difference":0}
    assert result["geometry_equality_proven"] is False


def test_same_count_different_visible_id_fails():
    spec, trials = parity_fixture()
    trials[1]["measurement"]["viewport_snapshots"][0]["visible_ids"] = ["a","c"]
    result = compare_rendered_trials(trials,spec,{"a","b","c"})
    assert result["state"] == "FAIL_RENDERED_ID_PARITY"
    assert result["records"][0]["sets"]["ids"]["a_only"] == ["b"]
    assert result["records"][0]["sets"]["ids"]["b_only"] == ["c"]


def test_late_pan_omission_cannot_hide_behind_initial_parity():
    spec, trials = parity_fixture()
    trials[1]["measurement"]["viewport_snapshots"][1]["visible_ids"] = []
    trials[1]["measurement"]["viewport_snapshots"][1]["rendered_fragment_count"] = 0
    result = compare_rendered_trials(trials,spec,{"a","b"})
    assert result["records"][0]["state"] == "PASS"
    assert result["records"][1]["state"] == "FAIL"


def test_both_arms_omitting_control_feature_fails_oracle():
    spec, trials = parity_fixture()
    spec["viewports"][0]["expected_visible_ids"] = {"initial":["a","b","c"]}
    result = compare_rendered_trials(trials,spec,{"a","b","c"})
    assert "INDEPENDENT_VISIBLE_ID_EXPECTATION_FAILED" in result["records"][0]["errors"]


@pytest.mark.parametrize("mutation,error", [
    (lambda t: t.pop(), "MISSING_RENDERED_TRIALS"),
    (lambda t: t.append(deepcopy(t[0])), "DUPLICATE_RENDERED_TRIAL"),
    (lambda t: t[1]["measurement"]["viewport_snapshots"].pop(), "MISSING_DUPLICATE"),
    (lambda t: t[1]["measurement"]["viewport_snapshots"][0].update(visible_ids=["a","a"]), "DUPLICATE_RENDERED_ID"),
    (lambda t: t[1]["measurement"]["viewport_snapshots"][0].update(visible_ids=[None]), "INVALID_RENDERED_ID"),
    (lambda t: t[1].update(repetition=True), "INTEGER_TRIAL"),
])
def test_malformed_trials_fail_closed(mutation,error):
    spec, trials = parity_fixture(); mutation(trials)
    with pytest.raises(ValueError,match=error):
        compare_rendered_trials(trials,spec,{"a","b"})


def test_camera_mismatch_blocks_apparent_parity():
    spec, trials = parity_fixture()
    trials[1]["measurement"]["viewport_snapshots"][1]["camera"]["zoom"] = 10
    result = compare_rendered_trials(trials,spec,{"a","b"})
    assert "mvt:CAMERA_TARGET_MISMATCH" in result["records"][1]["errors"]


def test_unknown_rendered_ids_block_both_matching_arms():
    spec, trials = parity_fixture()
    result = compare_rendered_trials(trials,spec,{"a"})
    assert result["state"] == "FAIL_RENDERED_ID_PARITY"
    assert result["records"][0]["unknown_ids"]["geojson"] == ["b"]


def test_explicit_empty_views_must_still_match():
    spec, trials = parity_fixture(); spec["viewports"][0]["expect_nonempty"] = False
    for trial in trials:
        for snapshot in trial["measurement"]["viewport_snapshots"]:
            snapshot["visible_ids"] = []; snapshot["rendered_fragment_count"] = 0
    assert compare_rendered_trials(trials,spec,{"a"})["state"] == "PASS_RENDERED_ID_PARITY"


def test_synthetic_real_engine_fixture_has_bound_lineage(tmp_path):
    from tools.gis_evidence.synthetic_smoke import prepare_fixture
    from tools.gis_evidence.core import load_geojson
    spec=prepare_fixture(tmp_path/"smoke",{}, {})
    _, index=load_geojson(Path(spec["source_path"]),
                         spec["source_sha256"],"GEOID")
    assert set(index)=={"SYNTHETIC:A","SYNTHETIC:B","SYNTHETIC:C"}
    assert admit_source_lineage(spec)["state"]=="PASS_STRUCTURAL_ARTIFACT_BINDING"
    assert spec["data_kind"]=="SYNTHETIC_TEST_ONLY" and spec["repetitions"]==5
    assert preflight(spec)["state"]=="BLOCKED"  # Real runtimes deliberately absent.


@pytest.mark.parametrize("omit_pan_id", [False, True])
def test_runner_consumes_viewport_gate_not_just_standalone_function(tmp_path, monkeypatch, omit_pan_id):
    """Orchestration test with stubbed engines; not real-engine performance."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    import sys
    from tools.gis_evidence import delivery_benchmark as module
    from tools.gis_evidence.synthetic_smoke import prepare_fixture
    spec=prepare_fixture(tmp_path/"inputs",{}, {"version":"UNIT_TEST_STUB"})
    original_source=Path(spec["source_path"]).read_bytes()
    out=tmp_path/"outputs"; out.mkdir()
    monkeypatch.setattr(module,"preflight",lambda s:{"state":"READY"})
    staged=[]

    @contextmanager
    def fake_martin(s, _):
        staged.append(s["source_path"])
        assert Path(s["source_path"]).read_bytes()==original_source
        yield "http://127.0.0.1:3000"

    @contextmanager
    def fake_fixture(s, base):
        assert s["source_path"]==staged[0]
        yield "http://127.0.0.1:4000", []

    class Page:
        def goto(self, *args): pass
        def wait_for_function(self, *args): pass
        def evaluate(self, code, cfg):
            snapshots=[]
            targets=[cfg["center"]]+cfg["pan_path"]
            for i,target in enumerate(targets):
                ids=["SYNTHETIC:C"] if i==1 else ["SYNTHETIC:A","SYNTHETIC:B"]
                if i==1 and cfg["mode"]=="mvt" and omit_pan_id:
                    ids=["SYNTHETIC:B"]
                snapshots.append({"step_id":"initial" if i==0 else f"pan:{i-1}",
                    "visible_ids":ids,"rendered_fragment_count":len(ids),
                    "camera":{"center":target,"zoom":cfg["zoom"],"pitch":0,"bearing":0,
                              "canvas_pixels":[1280,800]}})
            return {"maplibre_version":"UNIT_TEST_STUB","viewport_snapshots":snapshots,
                    "time_to_data_idle_ms":1,"peak_main_thread_js_heap_bytes":None}

    class Context:
        def route(self,*args): pass
        def new_page(self): return Page()
        def close(self): pass

    class Browser:
        version="UNIT_TEST_STUB_NOT_A_BROWSER"
        def new_context(self,**kwargs): return Context()
        def close(self): pass

    @contextmanager
    def fake_playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs:Browser()))

    monkeypatch.setitem(sys.modules,"playwright.sync_api",SimpleNamespace(sync_playwright=fake_playwright))
    monkeypatch.setattr(module,"martin_server",fake_martin)
    monkeypatch.setattr(module,"fixture_server",fake_fixture)
    monkeypatch.setattr(module,"reconstruct_ids",lambda *args:{"state":"PASS","fixture":"STUBBED_TILE_ID_GATE"})
    result=module.run(spec,out)
    assert spec["source_path"]!=staged[0]  # Caller spec is not mutated.
    assert Path(spec["source_path"]).read_bytes()==original_source
    expected="FAIL_VIEWPORT_PARITY" if omit_pan_id else "MEASURED_NOT_PUBLISHED"
    assert result["state"]==expected
    assert (out/"rendered-parity.json").exists()
    if omit_pan_id:
        assert result["rendered_parity"]["failed_checkpoint_count"]==10
        assert result["mvt_canonical"] is False
    else:
        assert result["rendered_parity"]["paired_checkpoint_count"]==30
        assert result["summary"]["automatic_publication"] is False
