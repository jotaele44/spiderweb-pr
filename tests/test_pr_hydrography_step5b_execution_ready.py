from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path

import pytest

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
from scripts.source_adapters.pr_hydrography.step5b_transaction import canonical_tree_manifest


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
    return {
        "source": "tiger", "source_id": "TIGER_PR_BOUNDARY", "raw_role": "RAW_REMOTE_ZIP",
        "raw_path": str(archive), "schema_fingerprint": "stage-schema", "receipts": [],
    }


def _nid_stage(tmp_path: Path) -> dict:
    path = tmp_path / "nid.geojson"
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"NID_ID": "PR00001", "DAM_NAME": "A"}, "geometry": None},
        {"type": "Feature", "properties": {"NID_ID": "PR00002", "DAM_NAME": "B"}, "geometry": None},
    ]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return {
        "source": "nid", "source_id": "USACE_NID_DAMS", "raw_role": "RAW_REMOTE_GEOJSON",
        "raw_path": str(path), "schema_fingerprint": "stage-schema", "receipts": [],
    }


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
        return {
            "source": source, "source_id": "USGS_NHD_WATERBODY", "raw_role": "RAW_PAGE_SET",
            "raw_page_set": {"page_set_sha256": hashlib.sha256(b"pages").hexdigest(), "pages": [
                {"raw_path": str(path), "offset": 0, "request_signature": "r", "receipt_id": "x", "raw_bytes_length": path.stat().st_size, "raw_bytes_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            ]}, "schema_fingerprint": "s", "receipts": [],
        }
    if source == "inland-bathy":
        meta = tmp_path / "bathy_meta.json"
        meta.write_text("{}", encoding="utf-8")
        return {
            "source": source, "source_id": "USGS_INLAND_BATHY_V4", "raw_role": "RAW_METADATA_PLUS_REMOTE_ZIP",
            "metadata_raw_path": str(meta), "archive_raw_path": str(path), "schema_fingerprint": "s", "receipts": [],
        }
    return {
        "source": source,
        "source_id": "TIGER_PR_BOUNDARY" if source == "tiger" else "USACE_NID_DAMS",
        "raw_role": "RAW_REMOTE_ZIP" if source == "tiger" else "RAW_REMOTE_GEOJSON",
        "raw_path": str(path), "schema_fingerprint": "s", "receipts": [],
    }


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


def test_schema_drift_requires_unresolved_delta_and_blocks(tmp_path: Path):
    delta = adjudicate_delta(source="nid", change_state="SCHEMA_CHANGED", old_denominator=36, new_denominator=36, schema_changed=True, semantic_delta_count=0)
    assert delta["classification"] == "UNRESOLVED"
    assert delta["promotion_safe"] is False


def test_snapshot_manifest_is_content_addressed_and_excludes_derivatives(tmp_path: Path):
    stages = [_source_stage(tmp_path, s) for s in ("tiger", "nhd", "nid", "inland-bathy")]
    first = snapshot_content_manifest(stages)
    second = snapshot_content_manifest(stages)
    assert first["snapshot_set_id"] == second["snapshot_set_id"]
    assert all(source["raw_role"].startswith("RAW_") for source in first["sources"])
