from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path

import pytest

from scripts.source_adapters.pr_hydrography.cli import FetchReceipt, audit_raw_receipt_accounting
from scripts.source_adapters.pr_hydrography.live_acquisition import (
    create_run_layout,
    promote_snapshot_set,
    snapshot_content_manifest,
    transaction_gate,
    write_run_document,
)
from scripts.source_adapters.pr_hydrography.step5b_certify import (
    adjudicate_delta,
    certify_fresh_nid,
    certify_fresh_tiger,
)
from scripts.source_adapters.pr_hydrography.step5b_transaction import canonical_tree_manifest, nhd_page_set_manifest


def _write_dbf(path: Path) -> None:
    fields = [("STATEFP", b"C", 2), ("NAME", b"C", 20)]
    rows = [("72", "Puerto Rico"), ("01", "Alabama")]
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(length for _, _, length in fields)
    header = bytearray(32)
    header[0] = 3
    header[4:8] = struct.pack("<I", len(rows))
    header[8:10] = struct.pack("<H", header_len)
    header[10:12] = struct.pack("<H", record_len)
    descriptors = bytearray()
    for name, field_type, length in fields:
        desc = bytearray(32)
        desc[: len(name)] = name.encode("ascii")
        desc[11:12] = field_type
        desc[16] = length
        descriptors.extend(desc)
    body = bytearray()
    for statefp, name in rows:
        body.extend(b" " + statefp.encode().ljust(2) + name.encode().ljust(20))
    path.write_bytes(bytes(header) + bytes(descriptors) + b"\r" + bytes(body) + b"\x1a")


def _tiger_stage(tmp_path: Path) -> dict:
    dbf = tmp_path / "state.dbf"
    _write_dbf(dbf)
    archive = tmp_path / "tiger.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(dbf, "tl_state.dbf")
        zf.writestr("tl_state.shp", b"shp")
    return {"source": "tiger", "source_id": "TIGER_PR_BOUNDARY", "raw_role": "RAW_REMOTE_ZIP", "raw_path": str(archive), "schema_fingerprint": "stage-schema", "receipts": []}


def _nid_stage(tmp_path: Path) -> dict:
    path = tmp_path / "nid.geojson"
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"NID_ID": "PR00001", "DAM_NAME": "A"}, "geometry": None},
        {"type": "Feature", "properties": {"NID_ID": "PR00002", "DAM_NAME": "B"}, "geometry": None},
    ]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return {"source": "nid", "source_id": "USACE_NID_DAMS", "raw_role": "RAW_REMOTE_GEOJSON", "raw_path": str(path), "schema_fingerprint": "stage-schema", "receipts": []}


def test_fresh_tiger_certifier_reads_statefp_from_preserved_zip(tmp_path: Path):
    cert = certify_fresh_tiger(_tiger_stage(tmp_path))
    assert cert["certified"] is True
    assert cert["pr_rows"] == 1
    assert cert["row_count"] == 2


def test_fresh_nid_certifier_is_geojson_native(tmp_path: Path):
    cert = certify_fresh_nid(_nid_stage(tmp_path))
    assert cert["certified"] is True
    assert cert["pr_prefix_count"] == 2
    assert cert["duplicate_nid_id_count"] == 0


def test_run_layout_is_append_only(tmp_path: Path):
    layout = create_run_layout(runtime_root=tmp_path / "runtime", manifest_root=tmp_path / "manifest", run_id="RUN1")
    write_run_document(layout["run_root"], "preflight.json", {"state": "PASS"})
    with pytest.raises(FileExistsError):
        write_run_document(layout["run_root"], "preflight.json", {"state": "PASS2"})
    with pytest.raises(FileExistsError):
        create_run_layout(runtime_root=tmp_path / "runtime", manifest_root=tmp_path / "manifest", run_id="RUN1")


def _source_stage(tmp_path: Path, source: str) -> dict:
    path = tmp_path / f"{source}.bin"
    path.write_bytes(source.encode())
    if source == "nhd":
        return {"source": source, "source_id": "USGS_NHD_WATERBODY", "raw_role": "RAW_PAGE_SET", "raw_page_set": {"page_set_sha256": hashlib.sha256(b"pages").hexdigest(), "pages": [{"raw_path": str(path), "offset": 0, "request_signature": "r", "receipt_id": "x", "raw_bytes_length": path.stat().st_size, "raw_bytes_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}, "schema_fingerprint": "s", "receipts": []}
    if source == "inland-bathy":
        meta = tmp_path / "bathy_meta.json"
        meta.write_text("{}", encoding="utf-8")
        return {"source": source, "source_id": "USGS_INLAND_BATHY_V4", "raw_role": "RAW_METADATA_PLUS_REMOTE_ZIP", "metadata_raw_path": str(meta), "archive_raw_path": str(path), "schema_fingerprint": "s", "receipts": []}
    return {"source": source, "source_id": "TIGER_PR_BOUNDARY" if source == "tiger" else "USACE_NID_DAMS", "raw_role": "RAW_REMOTE_ZIP" if source == "tiger" else "RAW_REMOTE_GEOJSON", "raw_path": str(path), "schema_fingerprint": "s", "receipts": []}


def _parent(tmp_path: Path):
    root = tmp_path / "parent"
    root.mkdir()
    (root / "f").write_text("frozen", encoding="utf-8")
    return root, canonical_tree_manifest(root)


def test_failure_injection_source2_and_source4_block_promotion(tmp_path: Path):
    parent_root, before = _parent(tmp_path)
    for sources in ({"tiger"}, {"tiger", "nhd", "nid"}):
        stages = [_source_stage(tmp_path, s) for s in sorted(sources)]
        certs = [{"source": s, "certified": True} for s in sources]
        changes = [{"source": s, "classification": "NO_CHANGE"} for s in sources]
        gate = transaction_gate(stages=stages, certifications=certs, change_records=changes, delta_records=[], raw_root=tmp_path, parent_before=before, parent_after=canonical_tree_manifest(parent_root))
        assert gate["state"].startswith("BLOCKED_")
        with pytest.raises(RuntimeError):
            promote_snapshot_set(stages=stages, gate=gate, snapshot_root=tmp_path / "snapshots")


def test_parent_mutation_blocks_promotion(tmp_path: Path):
    parent_root, before = _parent(tmp_path)
    stages = [_source_stage(tmp_path, s) for s in ("tiger", "nhd", "nid", "inland-bathy")]
    certs = [{"source": s, "certified": True} for s in ("tiger", "nhd", "nid", "inland-bathy")]
    changes = [{"source": s, "classification": "NO_CHANGE"} for s in ("tiger", "nhd", "nid", "inland-bathy")]
    (parent_root / "f").write_text("mutated", encoding="utf-8")
    gate = transaction_gate(stages=stages, certifications=certs, change_records=changes, delta_records=[], raw_root=tmp_path, parent_before=before, parent_after=canonical_tree_manifest(parent_root))
    assert gate["gates"]["historical_parent_mutations_zero"] is False
    assert gate["state"].startswith("BLOCKED_")


def test_schema_drift_requires_unresolved_delta_and_blocks():
    delta = adjudicate_delta(source="nid", change_state="SCHEMA_CHANGED", old_denominator=36, new_denominator=36, schema_changed=True, semantic_delta_count=0)
    assert delta["classification"] == "UNRESOLVED"
    assert delta["promotion_safe"] is False


def test_snapshot_manifest_is_content_addressed_and_excludes_derivatives(tmp_path: Path):
    stages = [_source_stage(tmp_path, s) for s in ("tiger", "nhd", "nid", "inland-bathy")]
    first = snapshot_content_manifest(stages)
    second = snapshot_content_manifest(stages)
    assert first["snapshot_set_id"] == second["snapshot_set_id"]
    assert all(source["raw_role"].startswith("RAW_") for source in first["sources"])


def _receipt(path: Path, token: str, *, offset: int | None = None) -> dict:
    return {
        "receipt_id": token,
        "raw_path": str(path.resolve()),
        "raw_bytes_length": path.stat().st_size,
        "raw_bytes_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "page_offset": offset,
    }


def test_raw_orphan_receipt_orphan_and_hash_mismatch_are_explicit(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    a = raw / "a.bin"
    a.write_bytes(b"a")
    orphan = audit_raw_receipt_accounting(raw, [])
    assert orphan["orphan_raw_files"] and not orphan["zero_unaccounted_response_bytes"]

    missing_path = raw / "missing.bin"
    missing_receipt = {"receipt_id": "m", "raw_path": str(missing_path), "raw_bytes_length": 1, "raw_bytes_sha256": hashlib.sha256(b"m").hexdigest()}
    missing = audit_raw_receipt_accounting(raw, [missing_receipt])
    assert missing["missing_receipt_targets"] and not missing["zero_unaccounted_response_bytes"]

    wrong_hash = _receipt(a, "a")
    wrong_hash["raw_bytes_sha256"] = "0" * 64
    mismatch = audit_raw_receipt_accounting(raw, [wrong_hash])
    assert mismatch["hash_mismatch_receipt_targets"] and not mismatch["zero_unaccounted_response_bytes"]


def _fetch_receipt(path: Path, token: str, offset: int) -> FetchReceipt:
    return FetchReceipt(
        receipt_id=token, source_id="USGS_NHD_WATERBODY", requested_url="https://example.invalid",
        final_url="https://example.invalid", http_status=200, response_headers={}, content_type="application/geo+json",
        content_length=str(path.stat().st_size), etag="", last_modified="", retrieval_utc="2026-08-13T00:00:00Z",
        fetch_backend="test", fetch_backend_version="1", raw_bytes_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        raw_bytes_length=path.stat().st_size, request_signature=token, expected_content="geojson", transport_state="OK",
        failure_class="", raw_path=str(path), page_offset=offset,
    )


def test_nhd_page_gap_is_rejected(tmp_path: Path):
    p0 = tmp_path / "p0"
    p1 = tmp_path / "p1"
    p0.write_bytes(b"0")
    p1.write_bytes(b"1")
    receipts = [_fetch_receipt(p0, "r0", 0), _fetch_receipt(p1, "r1", 4000)]
    with pytest.raises(RuntimeError, match="NHD_PAGE_GAP"):
        nhd_page_set_manifest(receipts, [2000, 10])


def test_positive_four_source_gate_and_atomic_promotion(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    stages = []
    source_ids = {"tiger": "TIGER_PR_BOUNDARY", "nhd": "USGS_NHD_WATERBODY", "nid": "USACE_NID_DAMS", "inland-bathy": "USGS_INLAND_BATHY_V4"}
    for source in ("tiger", "nhd", "nid", "inland-bathy"):
        p = raw / f"{source}.bin"
        p.write_bytes(source.encode())
        receipt = _receipt(p, source, offset=0 if source == "nhd" else None)
        if source == "nhd":
            stage = {"source": source, "source_id": source_ids[source], "raw_role": "RAW_PAGE_SET", "raw_page_set": {"page_set_sha256": "pages", "pages": [{"raw_path": str(p), "offset": 0, "request_signature": "r", "receipt_id": source, "raw_bytes_length": p.stat().st_size, "raw_bytes_sha256": receipt["raw_bytes_sha256"]}]}, "schema_fingerprint": "s", "receipts": [receipt]}
        elif source == "inland-bathy":
            meta = raw / "inland-bathy-meta.json"
            meta.write_text("{}", encoding="utf-8")
            meta_receipt = _receipt(meta, "bathy-meta")
            stage = {"source": source, "source_id": source_ids[source], "raw_role": "RAW_METADATA_PLUS_REMOTE_ZIP", "metadata_raw_path": str(meta), "archive_raw_path": str(p), "schema_fingerprint": "s", "receipts": [meta_receipt, receipt]}
        else:
            stage = {"source": source, "source_id": source_ids[source], "raw_role": "RAW_REMOTE_ZIP" if source == "tiger" else "RAW_REMOTE_GEOJSON", "raw_path": str(p), "schema_fingerprint": "s", "receipts": [receipt]}
        stages.append(stage)
    parent_root = tmp_path / "parent"
    parent_root.mkdir()
    (parent_root / "f").write_text("frozen", encoding="utf-8")
    before = canonical_tree_manifest(parent_root)
    certs = [{"source": s, "certified": True} for s in source_ids]
    changes = [{"source": s, "classification": "NO_CHANGE"} for s in source_ids]
    gate = transaction_gate(stages=stages, certifications=certs, change_records=changes, delta_records=[], raw_root=raw, parent_before=before, parent_after=canonical_tree_manifest(parent_root))
    assert gate["state"] == "PASS_STEP5B_TRANSACTIONAL_EXECUTION_READY"
    promoted = promote_snapshot_set(stages=stages, gate=gate, snapshot_root=tmp_path / "snapshots")
    assert promoted["state"] == "PASS_STEP5B_SNAPSHOT_SET_PROMOTED"
    assert Path(promoted["snapshot_path"]).is_dir()
    assert (Path(promoted["snapshot_path"]) / "content_manifest.json").is_file()
