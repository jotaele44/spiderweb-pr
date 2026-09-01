from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.source_adapters.pr_hydrography.cli import FetchReceipt
from scripts.source_adapters.pr_hydrography.step5b_stage import STAGED_PULLERS
from scripts.source_adapters.pr_hydrography.step5b_transaction import (
    REQUIRED_SOURCES,
    append_json_exclusive,
    canonical_tree_manifest,
    compare_tree_manifests,
    nhd_page_set_manifest,
    promotion_gate,
    write_individual_receipt,
)


def receipt(**overrides):
    base = FetchReceipt(
        receipt_id="R1",
        source_id="USGS_NHD_WATERBODY",
        requested_url="https://example.test/query?offset=0",
        final_url="https://example.test/query?offset=0",
        http_status=200,
        response_headers={"Content-Type": "application/geo+json"},
        content_type="application/geo+json",
        content_length="3",
        etag="",
        last_modified="",
        retrieval_utc="2026-08-13T04:00:00Z",
        fetch_backend="python_stdlib_urllib",
        fetch_backend_version="3.12",
        raw_bytes_sha256=hashlib.sha256(b"abc").hexdigest(),
        raw_bytes_length=3,
        request_signature="sig",
        expected_content="geojson",
        transport_state="OK",
        failure_class="",
        raw_path="/tmp/raw",
        page_offset=0,
    )
    return replace(base, **overrides)


def test_staged_pullers_cover_four_sources_and_do_not_expose_snapshot_promoter():
    assert set(STAGED_PULLERS) == REQUIRED_SOURCES
    for fn in STAGED_PULLERS.values():
        assert "_snapshot_payload" not in fn.__code__.co_names


def test_parent_tree_manifest_is_stable_and_detects_mutation(tmp_path: Path):
    root = tmp_path / "parent"
    root.mkdir()
    (root / "a").write_bytes(b"a")
    (root / "b").write_bytes(b"bb")
    before = canonical_tree_manifest(root)
    again = canonical_tree_manifest(root)
    assert before["tree_sha256"] == again["tree_sha256"]
    assert before["file_count"] == 2
    assert before["total_bytes"] == 3
    assert compare_tree_manifests(before, again)["historical_parent_mutations"] == 0
    (root / "b").write_bytes(b"changed")
    after = canonical_tree_manifest(root)
    assert compare_tree_manifests(before, after)["historical_parent_mutations"] == 1


def test_individual_receipt_write_is_append_only(tmp_path: Path):
    path = write_individual_receipt(tmp_path, receipt())
    assert path.exists()
    with pytest.raises(FileExistsError):
        write_individual_receipt(tmp_path, receipt())


def test_append_json_exclusive_is_append_only(tmp_path: Path):
    path = tmp_path / "x.json"
    append_json_exclusive(path, {"x": 1})
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        append_json_exclusive(path, {"x": 2})


def test_nhd_page_set_manifest_requires_unique_monotonic_offsets():
    p0 = receipt(receipt_id="R0", page_offset=0)
    p2 = receipt(receipt_id="R2", page_offset=2000, raw_bytes_length=7)
    manifest = nhd_page_set_manifest([p2, p0])
    assert manifest["page_count"] == 2
    assert [row["offset"] for row in manifest["pages"]] == [0, 2000]
    assert manifest["total_raw_bytes"] == 10
    with pytest.raises(RuntimeError):
        nhd_page_set_manifest([p0, replace(p0, receipt_id="RX")])


def test_global_promotion_gate_blocks_partial_four_source_run(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "f").write_bytes(b"frozen")
    frozen = canonical_tree_manifest(parent)
    blocked = promotion_gate(
        attempted_sources={"tiger", "nhd", "nid"},
        certified_sources={"tiger", "nhd", "nid"},
        raw_root=raw,
        receipts=[],
        parent_before=frozen,
        parent_after=frozen,
    )
    assert blocked["state"] == "BLOCKED_STEP5B_TRANSACTIONAL_EXECUTION"
    assert blocked["gates"]["all_required_sources_attempted"] is False


def test_global_promotion_gate_passes_only_complete_closed_run(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "f").write_bytes(b"frozen")
    frozen = canonical_tree_manifest(parent)
    report = promotion_gate(
        attempted_sources=set(REQUIRED_SOURCES),
        certified_sources=set(REQUIRED_SOURCES),
        raw_root=raw,
        receipts=[],
        parent_before=frozen,
        parent_after=frozen,
        unclassified_fetch_outcomes=0,
        unclassified_source_changes=0,
        unexplained_denominator_drift=0,
        silent_substitutions=0,
    )
    assert report["state"] == "PASS_STEP5B_TRANSACTIONAL_EXECUTION_READY"
    assert all(report["gates"].values())
