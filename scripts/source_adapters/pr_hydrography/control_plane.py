from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .core import SnapshotRecord, canonical_json, schema_fingerprint, sha256_file, utc_now

ARTIFACT_ROLES = (
    "SOURCE",
    "SNAPSHOT",
    "NORMALIZED_SOURCE",
    "DISCOVERY_CANDIDATE",
    "RANKED_CANDIDATE",
    "RELATIONSHIP",
    "CANONICAL_ENTITY",
    "HISTORICAL_ENTITY_STATE",
)

ALLOWED_TRANSFORMS = {
    ("SOURCE", "SNAPSHOT"),
    ("SNAPSHOT", "NORMALIZED_SOURCE"),
    ("NORMALIZED_SOURCE", "DISCOVERY_CANDIDATE"),
    ("DISCOVERY_CANDIDATE", "RANKED_CANDIDATE"),
    ("RANKED_CANDIDATE", "RELATIONSHIP"),
    ("RELATIONSHIP", "CANONICAL_ENTITY"),
    ("CANONICAL_ENTITY", "HISTORICAL_ENTITY_STATE"),
}

REMOTE_CHANGE_STATES = {
    "NO_CHANGE",
    "PAYLOAD_CHANGED_SCHEMA_STABLE",
    "SCHEMA_CHANGED",
    "ENDPOINT_CHANGED",
    "SOURCE_UNAVAILABLE",
    "UNEXPECTED_MEDIA",
    "SOURCE_EMPTY",
    "TRUE_CONTRADICTION",
}

TEMPORAL_STATES = {
    "CREATED",
    "OPERATIONAL",
    "SEDIMENTED",
    "RETIRED",
    "REPLACED",
    "RENAMED",
    "RECLASSIFIED",
    "UNDER_CONSTRUCTION",
    "PLANNED",
    "UNKNOWN",
}


@dataclass(frozen=True)
class TransformContract:
    transform_id: str
    input_role: str
    output_role: str
    version: str

    def validate(self) -> None:
        if self.input_role not in ARTIFACT_ROLES or self.output_role not in ARTIFACT_ROLES:
            raise ValueError("unknown artifact role")
        if (self.input_role, self.output_role) not in ALLOWED_TRANSFORMS:
            raise ValueError(f"forbidden role transition: {self.input_role}->{self.output_role}")


@dataclass(frozen=True)
class HistoricalImportRecord:
    source_id: str
    source_path: str
    bytes: int
    sha256: str
    media_type: str
    schema_fingerprint: str
    original_certification: str
    import_timestamp_utc: str
    expected_sha256: str
    binding_state: str


@dataclass(frozen=True)
class ChangeRecord:
    source_id: str
    previous_snapshot: str
    new_snapshot: str
    byte_change: str
    schema_change: str
    denominator_change: str
    entity_change: str
    relationship_change: str
    certification_effect: str
    classification: str


def validate_transform(contract: TransformContract) -> TransformContract:
    contract.validate()
    return contract


def bind_historical_file(
    path: Path,
    *,
    source_id: str,
    expected_sha256: str,
    media_type: str,
    original_certification: str,
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> HistoricalImportRecord:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    state = "EXACT_HASH_MATCH" if actual == expected_sha256 else "HASH_MISMATCH_UNRESOLVED"
    schema_fp = schema_fingerprint(rows or []) if rows is not None else ""
    return HistoricalImportRecord(
        source_id=source_id,
        source_path=str(path),
        bytes=path.stat().st_size,
        sha256=actual,
        media_type=media_type,
        schema_fingerprint=schema_fp,
        original_certification=original_certification,
        import_timestamp_utc=utc_now(),
        expected_sha256=expected_sha256,
        binding_state=state,
    )


def classify_remote_change(
    previous: SnapshotRecord | None,
    *,
    remote_sha256: str = "",
    remote_schema_fingerprint: str = "",
    endpoint_changed: bool = False,
    reachable: bool = True,
    media_expected: bool = True,
    payload_bytes: int | None = None,
    contradiction: bool = False,
) -> str:
    if contradiction:
        return "TRUE_CONTRADICTION"
    if not reachable:
        return "SOURCE_UNAVAILABLE"
    if endpoint_changed:
        return "ENDPOINT_CHANGED"
    if not media_expected:
        return "UNEXPECTED_MEDIA"
    if payload_bytes == 0:
        return "SOURCE_EMPTY"
    if previous is None:
        return "PAYLOAD_CHANGED_SCHEMA_STABLE"
    if remote_schema_fingerprint and remote_schema_fingerprint != previous.schema_fingerprint:
        return "SCHEMA_CHANGED"
    if remote_sha256 and remote_sha256 == previous.sha256:
        return "NO_CHANGE"
    return "PAYLOAD_CHANGED_SCHEMA_STABLE"


def require_classified_changes(states: Iterable[str]) -> None:
    bad = sorted({state for state in states if state not in REMOTE_CHANGE_STATES})
    if bad:
        raise RuntimeError(f"unclassified remote change state(s): {bad}")


def make_change_record(
    *,
    source_id: str,
    previous_snapshot: str,
    new_snapshot: str,
    classification: str,
    byte_change: str = "UNKNOWN",
    schema_change: str = "UNKNOWN",
    denominator_change: str = "UNKNOWN",
    entity_change: str = "UNKNOWN",
    relationship_change: str = "UNKNOWN",
    certification_effect: str = "REVIEW_REQUIRED",
) -> ChangeRecord:
    require_classified_changes([classification])
    return ChangeRecord(
        source_id=source_id,
        previous_snapshot=previous_snapshot,
        new_snapshot=new_snapshot,
        byte_change=byte_change,
        schema_change=schema_change,
        denominator_change=denominator_change,
        entity_change=entity_change,
        relationship_change=relationship_change,
        certification_effect=certification_effect,
        classification=classification,
    )


def canonical_logical_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def compare_replays(left: Any, right: Any) -> dict[str, Any]:
    left_fp = canonical_logical_fingerprint(left)
    right_fp = canonical_logical_fingerprint(right)
    return {
        "left": left_fp,
        "right": right_fp,
        "logical_equivalence": left_fp == right_fp,
        "byte_difference_requires_serialization_classification": left_fp == right_fp,
    }


def atomic_write_json(path: Path, document: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def rebuild_from_snapshot_store(snapshot_root: Path, output_root: Path) -> dict[str, Any]:
    """Minimal disaster-recovery inventory from persistent snapshots only.

    This deliberately ignores any Downloads-folder state. It proves the control
    plane can rediscover immutable snapshot metadata from a fresh checkout.
    """
    snapshot_root = Path(snapshot_root)
    output_root = Path(output_root)
    records = []
    for meta in sorted(snapshot_root.glob("*/*/snapshot.json")):
        document = json.loads(meta.read_text(encoding="utf-8"))
        payload = Path(document["payload_path"])
        if not payload.is_absolute():
            candidate = meta.parent / payload.name
            payload = candidate if candidate.exists() else payload
        if not payload.exists():
            raise RuntimeError(f"unaccounted snapshot payload: {payload}")
        if sha256_file(payload) != document["sha256"]:
            raise RuntimeError(f"snapshot payload hash mismatch: {payload}")
        records.append(document)
    report = {
        "schema": "spiderweb.pr_hydrography.disaster_recovery.v0_1",
        "snapshot_count": len(records),
        "records": records,
        "downloads_folder_required": False,
    }
    atomic_write_json(output_root / "recovery_inventory.json", report)
    return report


def temporal_state_record(entity_id: str, state: str, valid_from: str, valid_to: str = "", source_snapshot: str = "") -> dict[str, str]:
    if state not in TEMPORAL_STATES:
        raise ValueError(f"unknown temporal state: {state}")
    return {
        "entity_id": entity_id,
        "state": state,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_snapshot": source_snapshot,
    }


def certification_gate(
    *,
    unclassified_source_changes: int,
    unaccounted_bytes: int,
    schema_role_violations: int,
    proximity_only_identities: int,
    hidden_ties: int,
    unexplained_denominator_drift: int,
    canonical_overwrites: int,
    unbound_parent_snapshots: int,
) -> dict[str, Any]:
    values = locals().copy()
    passed = all(int(value) == 0 for value in values.values())
    return {"state": "PASS" if passed else "BLOCKED", **values}
