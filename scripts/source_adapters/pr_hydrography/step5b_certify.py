from __future__ import annotations

import json
import struct
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .certifiers import certify_inland_bathy_archive, certify_nhd_pages
from .control_plane import classify_remote_change, require_classified_changes
from .core import EXPECTED_V4_HARD_BINDINGS, SnapshotRecord, schema_fingerprint, sha256_file


CHANGE_STATES = {
    "NO_CHANGE",
    "PAYLOAD_CHANGED_SCHEMA_STABLE",
    "SCHEMA_CHANGED",
    "ENDPOINT_CHANGED",
    "SOURCE_UNAVAILABLE",
    "UNEXPECTED_MEDIA",
    "SOURCE_EMPTY",
    "TRUE_CONTRADICTION",
}


def _read_dbf_rows(payload: bytes) -> list[dict[str, str]]:
    """Read enough dBase III/IV to certify TIGER attributes without rewriting the source ZIP."""
    if len(payload) < 32:
        raise RuntimeError("SCHEMA_CHANGED: TIGER DBF header is truncated")
    record_count = struct.unpack("<I", payload[4:8])[0]
    header_length = struct.unpack("<H", payload[8:10])[0]
    record_length = struct.unpack("<H", payload[10:12])[0]
    if header_length < 33 or record_length < 2 or header_length > len(payload):
        raise RuntimeError("SCHEMA_CHANGED: TIGER DBF header lengths are invalid")
    fields: list[tuple[str, int]] = []
    pos = 32
    while pos + 32 <= header_length and payload[pos] != 0x0D:
        desc = payload[pos : pos + 32]
        name = desc[:11].split(b"\x00", 1)[0].decode("ascii", errors="strict").strip()
        length = int(desc[16])
        if not name or length <= 0:
            raise RuntimeError("SCHEMA_CHANGED: TIGER DBF has invalid field descriptor")
        fields.append((name, length))
        pos += 32
    if not fields:
        raise RuntimeError("SCHEMA_CHANGED: TIGER DBF has no fields")
    rows: list[dict[str, str]] = []
    offset = header_length
    for _ in range(record_count):
        record = payload[offset : offset + record_length]
        if len(record) != record_length:
            raise RuntimeError("PARTIAL_RESPONSE: TIGER DBF record is truncated")
        offset += record_length
        if record[:1] == b"*":
            continue
        cursor = 1
        row: dict[str, str] = {}
        for name, length in fields:
            raw = record[cursor : cursor + length]
            cursor += length
            row[name] = raw.decode("latin-1").strip()
        rows.append(row)
    return rows


def certify_fresh_tiger(stage: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(str(stage["raw_path"]))
    with zipfile.ZipFile(path) as archive:
        dbf_names = [name for name in archive.namelist() if name.lower().endswith(".dbf")]
        shp_names = [name for name in archive.namelist() if name.lower().endswith(".shp")]
        if len(dbf_names) != 1 or len(shp_names) != 1:
            raise RuntimeError("SCHEMA_CHANGED: TIGER archive must contain exactly one SHP and DBF")
        rows = _read_dbf_rows(archive.read(dbf_names[0]))
    pr_rows = [row for row in rows if row.get("STATEFP", "").strip() == "72"]
    if len(pr_rows) != 1:
        raise RuntimeError(f"SCHEMA_CHANGED: expected exactly one STATEFP=72 row; got {len(pr_rows)}")
    return {
        "source": "tiger",
        "source_id": stage["source_id"],
        "certified": True,
        "source_universe": "JURISDICTION_BOUNDARY",
        "row_count": len(rows),
        "pr_rows": 1,
        "schema_fingerprint": schema_fingerprint(rows),
        "raw_sha256": sha256_file(path),
        "zero_unclassified_rows": True,
    }


def certify_fresh_nhd(stage: Mapping[str, Any]) -> dict[str, Any]:
    pages = stage.get("page_features")
    if not isinstance(pages, list):
        raise RuntimeError("SCHEMA_CHANGED: staged NHD pages absent")
    property_pages: list[list[dict[str, Any]]] = []
    for features in pages:
        if not isinstance(features, list):
            raise RuntimeError("SCHEMA_CHANGED: staged NHD page is not a feature list")
        property_pages.append([dict(feature.get("properties") or {}) for feature in features])
    cert = certify_nhd_pages(property_pages)
    if cert["duplicate_pid_count"] or cert["unexpected_ftypes"] or not cert["arithmetic_closure"]:
        raise RuntimeError("SCHEMA_CHANGED: NHD source certification failed closure")
    return {"source": "nhd", "source_id": stage["source_id"], "certified": True, **cert}


def certify_fresh_nid(stage: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(str(stage["raw_path"]))
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("SOURCE_EMPTY: NID GeoJSON contains no features")
    rows = [dict(feature.get("properties") or {}) for feature in features]
    def nid_id(row: Mapping[str, Any]) -> str:
        for key in ("NID_ID", "NID ID", "nidId", "nid_id"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""
    ids = [nid_id(row) for row in rows]
    if any(not value for value in ids):
        raise RuntimeError("SCHEMA_CHANGED: NID GeoJSON contains null NID identifiers")
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise RuntimeError(f"SCHEMA_CHANGED: duplicate NID identifiers: {duplicates}")
    pr_ids = [value for value in ids if value.startswith("PR")]
    return {
        "source": "nid",
        "source_id": stage["source_id"],
        "certified": True,
        "source_universe": "NID_DAM_ASSET",
        "row_count": len(rows),
        "pr_prefix_count": len(pr_ids),
        "duplicate_nid_id_count": 0,
        "null_nid_id_count": 0,
        "schema_fingerprint": schema_fingerprint(rows),
        "raw_sha256": sha256_file(path),
        "raw_string_preservation": True,
        "normalization_derivative_only": True,
    }


def certify_fresh_bathy(
    stage: Mapping[str, Any],
    *,
    pr_subject_rows: Sequence[Mapping[str, Any]] | None,
    hard_bindings: Mapping[str, str] | None = None,
    survey_dois: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not stage.get("metadata_file_receipt_binding"):
        raise RuntimeError("SCHEMA_CHANGED: ScienceBase metadata/file receipt binding failed")
    if pr_subject_rows is None:
        raise RuntimeError("UNRESOLVED: Inland Bathymetry PR subject rows are required before promotion")
    path = Path(str(stage["archive_raw_path"]))
    cert = certify_inland_bathy_archive(
        path.read_bytes(),
        pr_subject_rows=pr_subject_rows,
        hard_bindings=hard_bindings or EXPECTED_V4_HARD_BINDINGS,
        survey_dois=survey_dois,
    )
    return {
        "source": "inland-bathy",
        "source_id": stage["source_id"],
        "certified": True,
        "raw_sha256": sha256_file(path),
        **cert,
    }


def snapshot_from_mapping(value: Mapping[str, Any] | None) -> SnapshotRecord | None:
    if value is None:
        return None
    return SnapshotRecord(**{field: value[field] for field in SnapshotRecord.__dataclass_fields__})


def classify_fresh_change(
    *,
    previous: Mapping[str, Any] | SnapshotRecord | None,
    fresh_sha256: str,
    fresh_schema_fingerprint: str,
    endpoint_changed: bool = False,
    reachable: bool = True,
    media_expected: bool = True,
    payload_bytes: int | None = None,
    contradiction: bool = False,
) -> str:
    previous_record = previous if isinstance(previous, SnapshotRecord) else snapshot_from_mapping(previous)
    state = classify_remote_change(
        previous_record,
        remote_sha256=fresh_sha256,
        remote_schema_fingerprint=fresh_schema_fingerprint,
        endpoint_changed=endpoint_changed,
        reachable=reachable,
        media_expected=media_expected,
        payload_bytes=payload_bytes,
        contradiction=contradiction,
    )
    require_classified_changes([state])
    if state not in CHANGE_STATES:
        raise RuntimeError(f"unclassified source change: {state}")
    return state


def adjudicate_delta(
    *,
    source: str,
    change_state: str,
    old_denominator: int | None,
    new_denominator: int | None,
    schema_changed: bool,
    semantic_delta_count: int | None,
) -> dict[str, Any]:
    require_classified_changes([change_state])
    denominator_delta = None if old_denominator is None or new_denominator is None else new_denominator - old_denominator
    if change_state == "NO_CHANGE":
        classification = "EXPECTED"
    elif change_state == "PAYLOAD_CHANGED_SCHEMA_STABLE" and denominator_delta == 0 and semantic_delta_count in (0, None):
        classification = "EXPLAINED"
    elif change_state == "PAYLOAD_CHANGED_SCHEMA_STABLE" and denominator_delta is not None and semantic_delta_count is not None:
        classification = "EXPLAINED"
    else:
        classification = "UNRESOLVED"
    return {
        "source": source,
        "change_state": change_state,
        "byte_bound_delta": change_state != "NO_CHANGE",
        "denominator_delta": denominator_delta,
        "schema_delta": bool(schema_changed),
        "semantic_delta_count": semantic_delta_count,
        "classification": classification,
        "promotion_safe": classification in {"EXPECTED", "EXPLAINED"},
    }
