from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import sha256_file
from .step5b_transaction import (
    PASS_PARENT,
    REQUIRED_SOURCES,
    append_json_exclusive,
    atomic_promote_directory,
    compare_tree_manifests,
    promotion_gate,
)

SCHEMA = "spiderweb.pr_hydrography.live_acquisition.v0_1"
RUN_FILES = (
    "preflight.json",
    "acquisition.json",
    "source_certifications.json",
    "change_classification.json",
    "delta_adjudication.json",
    "promotion.json",
    "final_certification.json",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def create_run_layout(*, runtime_root: Path, manifest_root: Path, run_id: str) -> dict[str, Path]:
    raw_root = runtime_root / "live_responses" / run_id / "raw"
    run_root = manifest_root / "live_runs" / run_id
    receipt_root = manifest_root / "live_receipts" / run_id / "receipts"
    if raw_root.parent.exists() or run_root.exists() or receipt_root.parent.exists():
        raise FileExistsError(f"Step5B run_id already exists: {run_id}")
    raw_root.mkdir(parents=True, exist_ok=False)
    run_root.mkdir(parents=True, exist_ok=False)
    receipt_root.mkdir(parents=True, exist_ok=False)
    return {"raw_root": raw_root, "run_root": run_root, "receipt_root": receipt_root}


def write_run_document(run_root: Path, name: str, document: Mapping[str, Any]) -> Path:
    if name not in RUN_FILES:
        raise ValueError(f"unknown Step5B run document: {name}")
    path = run_root / name
    append_json_exclusive(path, document)
    return path


def _raw_paths_for_stage(stage: Mapping[str, Any]) -> list[Path]:
    source = str(stage.get("source"))
    if source == "tiger" or source == "nid":
        return [Path(str(stage["raw_path"]))]
    if source == "nhd":
        pages = stage.get("raw_page_set", {}).get("pages", [])
        return [Path(str(page["raw_path"])) for page in pages]
    if source == "inland-bathy":
        return [Path(str(stage["metadata_raw_path"])), Path(str(stage["archive_raw_path"]))]
    raise RuntimeError(f"unknown staged source: {source}")


def snapshot_content_manifest(stages: Sequence[Mapping[str, Any]], *, parent_snapshot_set: str = PASS_PARENT) -> dict[str, Any]:
    sources = []
    for stage in sorted(stages, key=lambda row: str(row["source"])):
        files = []
        for path in _raw_paths_for_stage(stage):
            if not path.is_file():
                raise FileNotFoundError(path)
            files.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        sources.append({
            "source": stage["source"],
            "source_id": stage["source_id"],
            "raw_role": stage["raw_role"],
            "schema_fingerprint": stage.get("schema_fingerprint", ""),
            "raw_files": files,
            "nhd_page_set_sha256": stage.get("raw_page_set", {}).get("page_set_sha256", ""),
        })
    canonical_core = {"schema": SCHEMA, "parent_snapshot_set": parent_snapshot_set, "sources": sources}
    snapshot_set_id = hashlib.sha256(canonical_json_bytes(canonical_core)).hexdigest()
    return {**canonical_core, "snapshot_set_id": snapshot_set_id}


def _copy_stage_source(stage: Mapping[str, Any], destination: Path) -> None:
    source_dir = destination / "sources" / str(stage["source"])
    source_dir.mkdir(parents=True, exist_ok=False)
    for index, path in enumerate(_raw_paths_for_stage(stage)):
        target = source_dir / f"{index:03d}_{path.name}"
        shutil.copyfile(path, target)
        if target.stat().st_size != path.stat().st_size or sha256_file(target) != sha256_file(path):
            raise RuntimeError(f"HASH_FAILURE: promoted copy mismatch for {path}")


def promote_snapshot_set(
    *,
    stages: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
    snapshot_root: Path,
    parent_snapshot_set: str = PASS_PARENT,
) -> dict[str, Any]:
    if gate.get("state") != "PASS_STEP5B_TRANSACTIONAL_EXECUTION_READY":
        raise RuntimeError("partial or uncertified Step5B run cannot be promoted")
    if {str(stage.get("source")) for stage in stages} != REQUIRED_SOURCES:
        raise RuntimeError("snapshot promotion requires exactly the four required source families")
    manifest = snapshot_content_manifest(stages, parent_snapshot_set=parent_snapshot_set)
    final = snapshot_root / manifest["snapshot_set_id"]
    if final.exists():
        raise FileExistsError(final)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{manifest['snapshot_set_id']}.", dir=snapshot_root))
    try:
        for stage in stages:
            _copy_stage_source(stage, staging)
        append_json_exclusive(staging / "content_manifest.json", manifest)
        # Reverify all staged bytes before the atomic rename.
        for stage in stages:
            original = _raw_paths_for_stage(stage)
            copied = sorted((staging / "sources" / str(stage["source"])).iterdir())
            if len(original) != len(copied):
                raise RuntimeError("HASH_FAILURE: promoted source file count mismatch")
            for src, dst in zip(original, copied):
                if sha256_file(src) != sha256_file(dst):
                    raise RuntimeError("HASH_FAILURE: promoted source hash mismatch")
        atomic_promote_directory(staging, final)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"state": "PASS_STEP5B_SNAPSHOT_SET_PROMOTED", "snapshot_set_id": manifest["snapshot_set_id"], "snapshot_path": str(final), "content_manifest": manifest}


def update_latest_pointer(*, pointer_root: Path, source: str, snapshot_set_id: str) -> Path:
    """Noncanonical convenience pointer; only call after successful snapshot-set promotion."""
    pointer_root.mkdir(parents=True, exist_ok=True)
    path = pointer_root / f"{source}.json"
    payload = canonical_json_bytes({"source": source, "snapshot_set_id": snapshot_set_id}) + b"\n"
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=pointer_root)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def transaction_gate(
    *,
    stages: Sequence[Mapping[str, Any]],
    certifications: Sequence[Mapping[str, Any]],
    change_records: Sequence[Mapping[str, Any]],
    delta_records: Sequence[Mapping[str, Any]],
    raw_root: Path,
    parent_before: Mapping[str, Any],
    parent_after: Mapping[str, Any],
    unclassified_fetch_outcomes: int = 0,
    silent_substitutions: int = 0,
) -> dict[str, Any]:
    attempted = {str(stage.get("source")) for stage in stages}
    certified = {str(cert.get("source")) for cert in certifications if cert.get("certified") is True}
    receipts = [receipt for stage in stages for receipt in stage.get("receipts", [])]
    change_sources = {str(record.get("source")) for record in change_records}
    invalid_change_states = [record for record in change_records if record.get("classification") not in {
        "NO_CHANGE", "PAYLOAD_CHANGED_SCHEMA_STABLE", "SCHEMA_CHANGED", "ENDPOINT_CHANGED",
        "SOURCE_UNAVAILABLE", "UNEXPECTED_MEDIA", "SOURCE_EMPTY", "TRUE_CONTRADICTION",
    }]
    delta_by_source = {str(record.get("source")): record for record in delta_records}
    changed_sources = {str(record.get("source")) for record in change_records if record.get("classification") != "NO_CHANGE"}
    unexplained = sum(
        1 for source in changed_sources
        if source not in delta_by_source or not bool(delta_by_source[source].get("promotion_safe"))
    )
    unclassified_changes = len(invalid_change_states) + (0 if change_sources == REQUIRED_SOURCES else 1)
    base = promotion_gate(
        attempted_sources=attempted,
        certified_sources=certified,
        raw_root=raw_root,
        receipts=receipts,
        parent_before=parent_before,
        parent_after=parent_after,
        unclassified_fetch_outcomes=unclassified_fetch_outcomes,
        unclassified_source_changes=unclassified_changes,
        unexplained_denominator_drift=unexplained,
        silent_substitutions=silent_substitutions,
    )
    base["changed_sources"] = sorted(changed_sources)
    base["delta_adjudication_safe"] = unexplained == 0
    base["change_classification_complete"] = change_sources == REQUIRED_SOURCES and not invalid_change_states
    return base
