"""Fail-closed byte-identity gate for provisional grid V2 source snapshots.

This asserts that the materialization input is byte-identical to an explicitly
frozen source snapshot. It does NOT establish source authority, positional
accuracy, or correct upstream identification of real-world features.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spiderweb.geographic_grid_v2 import GridV2Error

SOURCE_CONTRACT = "pr-grid-v2-source-snapshot/1.0"
SOURCE_PROVENANCE_STATE = "BYTE_VERIFIED_AUTHORITY_UNRESOLVED"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset((
    "contract", "source_manifestation_id", "source_uri", "retrieval_utc",
    "snapshot_filename", "snapshot_sha256", "snapshot_bytes",
    "input_sha256", "input_bytes", "input_record_count",
    "transformation", "authority_evidence_state",
))


def strict_json(raw: str) -> Any:
    """Reject duplicate JSON object names and non-standard NaN/Infinity."""
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, value in items:
            if name in result:
                raise GridV2Error(f"duplicate JSON key: {name!r}")
            result[name] = value
        return result
    def forbidden(value: str) -> None:
        raise GridV2Error(f"invalid JSON numeric constant: {value}")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=forbidden)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GridV2Error("invalid JSON source/manifest bytes") from exc


def _sha_and_bytes(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    length = 0
    with path.open("rb") as stream:
        while payload := stream.read(1024 * 1024):
            h.update(payload)
            length += len(payload)
    return h.hexdigest(), length


def _require_uint(record: dict[str, Any], key: str) -> int:
    value = record[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GridV2Error(f"invalid unsigned integer in source manifest: {key}")
    return value


def _require_sha(record: dict[str, Any], key: str) -> str:
    value = record[key]
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise GridV2Error(f"invalid SHA256 in source manifest: {key}")
    return value


def verify_source_snapshot(
    manifest_path: Path, input_path: Path, *, record_count: int
) -> dict[str, Any]:
    """Verify frozen bytes and row counts; never infer authoritative lineage."""
    manifest_path = manifest_path.resolve(strict=True)
    input_path = input_path.resolve(strict=True)
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = strict_json(manifest_bytes.decode("utf-8"))
    except (UnicodeError, OSError) as exc:
        raise GridV2Error("unreadable source snapshot manifest") from exc
    if not isinstance(manifest, dict) or set(manifest) != _FIELDS:
        raise GridV2Error("source manifest field set mismatch")
    if manifest["contract"] != SOURCE_CONTRACT:
        raise GridV2Error("unsupported source snapshot manifest contract")
    if manifest["transformation"] != "BYTE_IDENTICAL":
        raise GridV2Error("unverified source-to-input transformation")
    if manifest["authority_evidence_state"] != "UNVERIFIED":
        raise GridV2Error("source authority is not verified by this contract")
    for key in ("source_manifestation_id", "source_uri"):
        value = manifest[key]
        if not isinstance(value, str) or not value.strip():
            raise GridV2Error(f"missing {key}")
    stamp = manifest["retrieval_utc"]
    if not isinstance(stamp, str) or not stamp.endswith("Z"):
        raise GridV2Error("retrieval_utc must be explicit UTC")
    try:
        d = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GridV2Error("invalid retrieval_utc timestamp") from exc
    if d.tzinfo is None or d.utcoffset() != timezone.utc.utcoffset(d):
        raise GridV2Error("retrieval_utc is not UTC")
    filename = manifest["snapshot_filename"]
    if (not isinstance(filename, str) or not filename or
            Path(filename).name != filename or filename in (".", "..") or
            "\\" in filename):
        raise GridV2Error("snapshot_filename must be a local basename")
    snapshot = (manifest_path.parent / filename).resolve(strict=True)
    if snapshot == input_path or snapshot == manifest_path:
        raise GridV2Error("input, snapshot and manifest must be distinct files")
    if manifest_path == input_path:
        raise GridV2Error("input and manifest cannot be the same file")
    expected_source_hash = _require_sha(manifest, "snapshot_sha256")
    expected_input_hash = _require_sha(manifest, "input_sha256")
    source_bytes = _require_uint(manifest, "snapshot_bytes")
    input_bytes = _require_uint(manifest, "input_bytes")
    expected_rows = _require_uint(manifest, "input_record_count")
    if expected_rows != record_count:
        raise GridV2Error("input record denominator mismatch")
    source_sha, observed_source_bytes = _sha_and_bytes(snapshot)
    input_sha, observed_input_bytes = _sha_and_bytes(input_path)
    if source_sha != expected_source_hash or observed_source_bytes != source_bytes:
        raise GridV2Error("snapshot frozen SHA256/byte-size mismatch")
    if input_sha != expected_input_hash or observed_input_bytes != input_bytes:
        raise GridV2Error("input frozen SHA256/byte-size mismatch")
    if source_sha != input_sha or source_bytes != input_bytes:
        raise GridV2Error("source snapshot is not byte-identical to input")
    # Two independent paths with the same digest prove byte identity,
    # not authoritative source manifestation or certified precision.
    return {
        "_Snapshot_Path": str(snapshot),
        "Source_Provenance_State": SOURCE_PROVENANCE_STATE,
        "Source_Manifestation_ID": manifest["source_manifestation_id"],
        "Source_URI": manifest["source_uri"],
        "Source_Retrieval_UTC": stamp,
        "Source_Snapshot_SHA256": source_sha,
        "Source_Snapshot_Bytes": source_bytes,
        "Source_Manifest_SHA256": hashlib.sha256(manifest_bytes).hexdigest(),
        "Source_Transformation": "BYTE_IDENTICAL",
        "Source_Authority_Evidence_State": "UNVERIFIED",
        "Input_Record_Count_Verified": expected_rows,
    }
