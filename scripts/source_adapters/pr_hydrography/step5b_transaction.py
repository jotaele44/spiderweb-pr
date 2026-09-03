from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .cli import FetchReceipt, audit_raw_receipt_accounting
from .core import sha256_file

SCHEMA = "spiderweb.pr_hydrography.step5b_transaction.v0_1"
PASS_PARENT = "PR_HYDROGRAPHY_2026_08_11_v2"
REQUIRED_SOURCES = {"tiger", "nhd", "nid", "inland-bathy"}


def canonical_tree_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    files = []
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        size = path.stat().st_size
        total += size
        files.append({"path": str(path.relative_to(root)), "bytes": size, "sha256": sha256_file(path)})
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"root": str(root), "file_count": len(files), "total_bytes": total, "tree_sha256": hashlib.sha256(canonical).hexdigest(), "files": files}


def compare_tree_manifests(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    same = before.get("tree_sha256") == after.get("tree_sha256") and before.get("file_count") == after.get("file_count") and before.get("total_bytes") == after.get("total_bytes")
    return {"same": same, "historical_parent_mutations": 0 if same else 1, "before_tree_sha256": before.get("tree_sha256"), "after_tree_sha256": after.get("tree_sha256")}


def append_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def write_individual_receipt(receipt_root: Path, receipt: FetchReceipt) -> Path:
    path = receipt_root / f"{receipt.receipt_id}.json"
    append_json_exclusive(path, asdict(receipt))
    return path


def nhd_page_set_manifest(receipts: list[FetchReceipt], feature_counts: Sequence[int] | None = None) -> dict[str, Any]:
    ordered = sorted(receipts, key=lambda r: (-1 if r.page_offset is None else r.page_offset))
    pages = []
    for index, receipt in enumerate(ordered):
        if receipt.page_offset is None:
            raise RuntimeError("NHD receipt missing page_offset")
        page = {"offset": receipt.page_offset, "request_signature": receipt.request_signature, "receipt_id": receipt.receipt_id, "raw_path": receipt.raw_path, "raw_bytes_length": receipt.raw_bytes_length, "raw_bytes_sha256": receipt.raw_bytes_sha256}
        if feature_counts is not None:
            page["feature_count"] = int(feature_counts[index])
        pages.append(page)
    offsets = [p["offset"] for p in pages]
    if offsets != sorted(set(offsets)):
        raise RuntimeError("NHD page offsets are duplicate or nonmonotonic")
    if offsets and offsets[0] != 0:
        raise RuntimeError("NHD page offsets must start at zero")
    if feature_counts is not None:
        if len(feature_counts) != len(pages):
            raise RuntimeError("NHD feature-count denominator does not match receipt denominator")
        for previous, current in zip(pages, pages[1:]):
            expected = int(previous["offset"]) + int(previous["feature_count"])
            if int(current["offset"]) != expected:
                raise RuntimeError(f"NHD_PAGE_GAP: expected offset {expected}; got {current['offset']}")
    canonical = json.dumps(pages, sort_keys=True, separators=(",", ":")).encode()
    return {"artifact_role": "RAW_PAGE_SET_MANIFEST", "source_id": "USGS_NHD_WATERBODY", "page_count": len(pages), "total_raw_bytes": sum(p["raw_bytes_length"] for p in pages), "page_set_sha256": hashlib.sha256(canonical).hexdigest(), "pages": pages}


def promotion_gate(*, attempted_sources: set[str], certified_sources: set[str], raw_root: Path, receipts: list[dict[str, Any]], parent_before: Mapping[str, Any], parent_after: Mapping[str, Any], unclassified_fetch_outcomes: int = 0, unclassified_source_changes: int = 0, unexplained_denominator_drift: int = 0, silent_substitutions: int = 0) -> dict[str, Any]:
    accounting = audit_raw_receipt_accounting(raw_root, receipts)
    parent = compare_tree_manifests(parent_before, parent_after)
    gates = {
        "all_required_sources_attempted": attempted_sources == REQUIRED_SOURCES,
        "all_required_sources_certified": certified_sources == REQUIRED_SOURCES,
        "unaccounted_response_bytes_zero": accounting["zero_unaccounted_response_bytes"],
        "unclassified_fetch_outcomes_zero": unclassified_fetch_outcomes == 0,
        "unclassified_source_changes_zero": unclassified_source_changes == 0,
        "unexplained_denominator_drift_zero": unexplained_denominator_drift == 0,
        "silent_substitutions_zero": silent_substitutions == 0,
        "historical_parent_mutations_zero": parent["historical_parent_mutations"] == 0,
    }
    return {"schema": SCHEMA, "pass_parent": PASS_PARENT, "gates": gates, "raw_accounting": accounting, "parent_immutability": parent, "state": "PASS_STEP5B_TRANSACTIONAL_EXECUTION_READY" if all(gates.values()) else "BLOCKED_STEP5B_TRANSACTIONAL_EXECUTION"}


def atomic_promote_directory(staging: Path, final: Path) -> None:
    staging = staging.resolve()
    final = final.resolve()
    if final.exists():
        raise FileExistsError(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, final)
