from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from scripts.source_adapters.pr_hydrography.certifiers import (
    certify_nhd_pages,
    certify_nid_csv,
    certify_tiger_pr,
    logical_certification_fingerprint,
)
from scripts.source_adapters.pr_hydrography.cli import (
    FetchReceipt,
    _append_receipt_set,
    _atomic_exact_write,
    compare_parent_tree,
    step5a_readiness,
)
from scripts.source_adapters.pr_hydrography.control_plane import (
    TransformContract,
    bind_historical_file,
    certification_gate,
    classify_remote_change,
    compare_replays,
    rebuild_from_snapshot_store,
    temporal_state_record,
    validate_transform,
)
from scripts.source_adapters.pr_hydrography.core import (
    ImmutableSnapshotStore,
    SOURCE_SPECS,
    SnapshotRecord,
    matching_text,
    request_signature,
)
from scripts.source_adapters.pr_hydrography.spine import build_spine
from scripts.source_adapters.pr_hydrography.transport import (
    STEP5A_FAILURE_CLASSES,
    classify_transport_outcome,
    step5a_failure_class,
)
from scripts.source_adapters.pr_hydrography.validation import analysis_geometry


def snapshot(**overrides):
    base = SnapshotRecord(
        snapshot_id="S1",
        source_id="USGS_NHD_WATERBODY",
        adapter_version="v0",
        request_signature="r",
        source_update_date="2026-08-11",
        sha256="abc",
        bytes=3,
        schema_fingerprint="schema-a",
        acquired_utc="2026-08-11T00:00:00Z",
        parent_snapshot="",
        payload_path="payload",
        state="SNAPSHOT_CREATED",
    )
    return replace(base, **overrides)


def test_artifact_role_registry_rejects_skips():
    validate_transform(TransformContract("ok", "SOURCE", "SNAPSHOT", "1"))
    with pytest.raises(ValueError):
        validate_transform(TransformContract("bad", "SOURCE", "CANONICAL_ENTITY", "1"))


def test_remote_change_matrix():
    prev = snapshot()
    assert classify_remote_change(prev, remote_sha256="abc", remote_schema_fingerprint="schema-a") == "NO_CHANGE"
    assert classify_remote_change(prev, remote_sha256="def", remote_schema_fingerprint="schema-a") == "PAYLOAD_CHANGED_SCHEMA_STABLE"
    assert classify_remote_change(prev, remote_sha256="def", remote_schema_fingerprint="schema-b") == "SCHEMA_CHANGED"
    assert classify_remote_change(prev, reachable=False) == "SOURCE_UNAVAILABLE"
    assert classify_remote_change(prev, endpoint_changed=True) == "ENDPOINT_CHANGED"
    assert classify_remote_change(prev, media_expected=False) == "UNEXPECTED_MEDIA"
    assert classify_remote_change(prev, payload_bytes=0) == "SOURCE_EMPTY"
    assert classify_remote_change(prev, contradiction=True) == "TRUE_CONTRADICTION"


def test_transport_adversarial_matrix():
    assert classify_transport_outcome(status=200, content_type="application/json", payload=b'{"ok":1}', expected_content="json") == "OK"
    assert classify_transport_outcome(status=302, content_type="text/plain", payload=b"redirect", expected_content="json") == "HTTP_REDIRECT"
    assert classify_transport_outcome(status=429, content_type="text/plain", payload=b"slow", expected_content="json") == "RATE_LIMITED"
    assert classify_transport_outcome(status=200, content_type="application/json", payload=b"", expected_content="json") == "EMPTY_RESPONSE"
    assert classify_transport_outcome(status=200, content_type="text/html", payload=b"<html>error</html>", expected_content="zip") == "UNEXPECTED_HTML"
    assert classify_transport_outcome(status=200, content_type="application/json", payload=b'{"broken"', expected_content="json") == "TRUNCATED_JSON"
    assert classify_transport_outcome(status=200, content_type="application/octet-stream", payload=b"PK\x03\x04abc", expected_content="zip", expected_bytes=100) == "PARTIAL_DOWNLOAD"
    assert classify_transport_outcome(status=200, content_type="application/octet-stream", payload=b"notzip", expected_content="zip") == "UNEXPECTED_MEDIA"
    assert classify_transport_outcome(status=None, content_type="", payload=b"", expected_content="json", timed_out=True) == "TIMEOUT"
    assert classify_transport_outcome(status=None, content_type="", payload=b"", expected_content="json", network_error=True) == "SOURCE_UNAVAILABLE"


def test_step5a_failure_ontology_is_closed_and_mapped():
    assert STEP5A_FAILURE_CLASSES == {
        "SOURCE_UNAVAILABLE",
        "UNEXPECTED_MEDIA",
        "SOURCE_EMPTY",
        "PARTIAL_RESPONSE",
        "REDIRECT_FAILURE",
        "HASH_FAILURE",
        "SCHEMA_CHANGED",
        "UNCLASSIFIED",
    }
    expected = {
        "TIMEOUT": "SOURCE_UNAVAILABLE",
        "SOURCE_UNAVAILABLE": "SOURCE_UNAVAILABLE",
        "RATE_LIMITED": "SOURCE_UNAVAILABLE",
        "EMPTY_RESPONSE": "SOURCE_EMPTY",
        "UNEXPECTED_HTML": "UNEXPECTED_MEDIA",
        "UNEXPECTED_MEDIA": "UNEXPECTED_MEDIA",
        "TRUNCATED_JSON": "PARTIAL_RESPONSE",
        "PARTIAL_DOWNLOAD": "PARTIAL_RESPONSE",
        "HTTP_REDIRECT": "REDIRECT_FAILURE",
    }
    assert {state: step5a_failure_class(state) for state in expected} == expected
    assert step5a_failure_class("NOT_A_STATE") == "UNCLASSIFIED"


def test_step5a_receipt_contract_and_readiness_gate():
    required = {
        "requested_url", "final_url", "http_status", "response_headers", "content_type",
        "content_length", "etag", "last_modified", "retrieval_utc", "fetch_backend",
        "fetch_backend_version", "raw_bytes_sha256", "raw_bytes_length",
    }
    assert required <= set(FetchReceipt.__dataclass_fields__)
    report = step5a_readiness()
    assert report["pass_parent"] == "PR_HYDROGRAPHY_2026_08_11_v2"
    assert all(report["gates"].values())
    assert report["state"] == "PASS_STEP5A_LIVE_ACQUISITION_PROVENANCE_READY"


def test_step5a_raw_writer_is_exact_and_append_only(tmp_path: Path):
    path = tmp_path / "raw" / "response.bin"
    payload = b"exact remote response bytes\x00\xff"
    _atomic_exact_write(path, payload)
    assert path.read_bytes() == payload
    assert hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
    with pytest.raises(FileExistsError):
        _atomic_exact_write(path, payload)


def test_step5a_parent_tree_comparison_detects_any_mutation():
    same = compare_parent_tree({"a": "1", "b": "2"}, {"a": "1", "b": "2"})
    assert same["historical_parent_mutations"] == 0
    changed = compare_parent_tree({"a": "1", "b": "2"}, {"a": "9", "c": "3"})
    assert changed["changed"] == ["a"]
    assert changed["removed"] == ["b"]
    assert changed["added"] == ["c"]
    assert changed["historical_parent_mutations"] == 3


def test_step5a_receipt_set_is_append_only(tmp_path: Path):
    report = {"run_id": "RUN001", "state": "PASS_STEP5A_LIVE_ACQUISITION_PROVENANCE_READY"}
    path = _append_receipt_set(tmp_path, report)
    assert path.exists()
    with pytest.raises(FileExistsError):
        _append_receipt_set(tmp_path, report)


def test_historical_byte_binding_exact_and_mismatch(tmp_path: Path):
    path = tmp_path / "raw.bin"
    path.write_bytes(b"abc")
    digest = hashlib.sha256(b"abc").hexdigest()
    exact = bind_historical_file(path, source_id="X", expected_sha256=digest, media_type="application/octet-stream", original_certification="C")
    assert exact.binding_state == "EXACT_HASH_MATCH"
    mismatch = bind_historical_file(path, source_id="X", expected_sha256="0" * 64, media_type="application/octet-stream", original_certification="C")
    assert mismatch.binding_state == "HASH_MISMATCH_UNRESOLVED"


def test_nid_header_shift_preamble_column_reorder_mojibake_and_duplicates():
    payload = (
        "Data Last Updated:,2026-8-10\n"
        "noise,metadata\n"
        "State,Dam Name,NID ID,Other Names\n"
        "PR,Ana Mariaâ\u00a0Ii Dam,PR00029,Ana Maria II Dam\n"
        "PR,Rio Â\u00a0Blanco Dam,PR00078,Rio Blanco Offstream Dam\n"
        "PR,Rio Blanco duplicate,PR00078,Rio Blanco Offstream Dam\n"
    ).encode("utf-8")
    cert = certify_nid_csv(payload)
    assert cert["header_line_index"] == 2
    assert cert["pr_prefix_count"] == 3
    assert cert["pr_prefix_unique"] == 2
    assert cert["duplicate_pr_nid_ids"] == 1
    assert cert["prefix_state_set_equal"] is True
    assert matching_text("Ana Mariaâ\u00a0Ii Dam") == "ana maria ii dam"
    assert matching_text("Rio Â\u00a0Blanco Dam") == "rio blanco dam"


def test_nhd_duplicate_pid_arithmetic_and_jurisdiction_gate():
    page = [
        {"PERMANENT_IDENTIFIER": "1", "FTYPE": 390},
        {"PERMANENT_IDENTIFIER": "2", "FTYPE": 436},
    ]
    cert = certify_nhd_pages([page], jurisdiction_states={"1": "WITHIN_PR", "2": "WITHIN_PR"})
    assert cert["arithmetic_closure"] is True
    assert cert["jurisdiction_unclassified"] == 0
    duplicate = certify_nhd_pages([page + [{"PERMANENT_IDENTIFIER": "1", "FTYPE": 390}]])
    assert duplicate["duplicate_pid_count"] == 1


def test_tiger_zero_unclassified_gate():
    cert = certify_tiger_pr([{"STATEFP": "72", "NAME": "Puerto Rico"}, {"STATEFP": "06", "NAME": "California"}])
    assert cert["pr_rows"] == 1
    assert cert["zero_unclassified_rows"] is True


def test_analysis_only_invalid_geometry_repair():
    geom = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    source_wkb = geom.wkb
    repaired, audit = analysis_geometry(geom)
    assert geom.wkb == source_wkb
    assert repaired.is_valid
    assert audit["source_mutated"] is False


def test_temporal_state_does_not_collapse_history():
    old = temporal_state_record("E1", "OPERATIONAL", "1950", "2000", "S1")
    new = temporal_state_record("E1", "SEDIMENTED", "2000", "", "S2")
    assert old["state"] != new["state"]
    assert old["valid_to"] == "2000"


def test_replay_logical_equivalence_independent_of_dict_order():
    left = {"b": 2, "a": [3, 1]}
    right = {"a": [3, 1], "b": 2}
    result = compare_replays(left, right)
    assert result["logical_equivalence"] is True


def test_snapshot_store_crash_restart_does_not_overwrite(tmp_path: Path):
    store = ImmutableSnapshotStore(tmp_path)
    spec = SOURCE_SPECS["USGS_NHD_WATERBODY"]
    first = store.write(spec, b"abc", request_sig=request_signature(spec.source_id, "GET", {}), schema_fp="s")
    assert Path(first.payload_path).read_bytes() == b"abc"
    second = store.write(spec, b"abcd", request_sig=request_signature(spec.source_id, "GET", {}), schema_fp="s", parent_snapshot=first.snapshot_id)
    assert first.snapshot_id != second.snapshot_id
    assert Path(first.payload_path).read_bytes() == b"abc"
    assert Path(second.payload_path).read_bytes() == b"abcd"


def test_disaster_recovery_from_snapshot_store_only(tmp_path: Path):
    store_root = tmp_path / "store"
    store = ImmutableSnapshotStore(store_root)
    spec = SOURCE_SPECS["USGS_NHD_WATERBODY"]
    store.write(spec, b"abc", request_sig="r", schema_fp="s")
    report = rebuild_from_snapshot_store(store_root, tmp_path / "out")
    assert report["snapshot_count"] == 1
    assert report["downloads_folder_required"] is False


def test_certification_gate_fail_closed():
    assert certification_gate(
        unclassified_source_changes=0,
        unaccounted_bytes=0,
        schema_role_violations=0,
        proximity_only_identities=0,
        hidden_ties=0,
        unexplained_denominator_drift=0,
        canonical_overwrites=0,
        unbound_parent_snapshots=0,
    )["state"] == "PASS"
    assert certification_gate(
        unclassified_source_changes=1,
        unaccounted_bytes=0,
        schema_role_violations=0,
        proximity_only_identities=0,
        hidden_ties=0,
        unexplained_denominator_drift=0,
        canonical_overwrites=0,
        unbound_parent_snapshots=0,
    )["state"] == "BLOCKED"


def test_spine_refuses_unresolved_relationships():
    rows = [{"source_universe": "RESERVOIR_ENTITY_2004", "canonical_entity_id": "E1", "canonical_name": "Carite", "temporal_state": "OPERATIONAL"}]
    with pytest.raises(RuntimeError):
        build_spine(rows, [{"nid_id": "PR00021", "relationship_status": "RELATIONSHIP_TOP_EVIDENCE_TIE_REVIEW"}])


def test_spine_builds_only_from_closed_relationships():
    rows = [
        {"source_universe": "RESERVOIR_ENTITY_2004", "canonical_entity_id": "E1", "canonical_name": "Carite", "temporal_state": "OPERATIONAL", "valid_from": "2004"},
        {"source_universe": "NID_DAM_ASSET", "canonical_entity_id": "E1", "canonical_name": "Carite", "nid_id": "PR00021", "temporal_state": "OPERATIONAL", "valid_from": "2026"},
    ]
    result = build_spine(rows, [{"nid_id": "PR00021", "relationship_status": "RELATIONSHIP_CONFIRMED_AUTHORITATIVE"}])
    assert result["entity_count"] == 1
    assert result["unresolved_relationship_rows"] == 0


def test_logical_fingerprint_deterministic():
    assert logical_certification_fingerprint({"b": 2, "a": 1}) == logical_certification_fingerprint({"a": 1, "b": 2})
