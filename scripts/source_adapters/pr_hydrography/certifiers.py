from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import canonical_pid, matching_text, schema_fingerprint, sha256_bytes


def certify_tiger_pr(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise RuntimeError("TIGER source is empty")
    pr_rows = [row for row in rows if str(row.get("STATEFP", "")).strip() == "72"]
    other = [row for row in rows if str(row.get("STATEFP", "")).strip() != "72"]
    if len(pr_rows) != 1:
        raise RuntimeError(f"expected exactly one Puerto Rico state row; got {len(pr_rows)}")
    return {
        "source_universe": "JURISDICTION_BOUNDARY",
        "rows": len(rows),
        "pr_rows": 1,
        "non_pr_rows": len(other),
        "statefp": "72",
        "schema_fingerprint": schema_fingerprint(rows),
        "zero_unclassified_rows": len(pr_rows) + len(other) == len(rows),
    }


def certify_nhd_pages(pages: Sequence[Sequence[Mapping[str, Any]]], excluded_pids: Sequence[str] = ()) -> dict[str, Any]:
    rows = [dict(row) for page in pages for row in page]
    if not rows:
        raise RuntimeError("NHD source is empty")
    pids = [canonical_pid(row.get("PERMANENT_IDENTIFIER")) for row in rows]
    if any(not pid for pid in pids):
        raise RuntimeError("NHD null permanent identifier")
    duplicates = [pid for pid, count in Counter(pids).items() if count > 1]
    excluded = {canonical_pid(pid) for pid in excluded_pids}
    retained = [row for row in rows if canonical_pid(row.get("PERMANENT_IDENTIFIER")) not in excluded]
    ftypes = Counter(int(row.get("FTYPE")) for row in retained)
    unexpected = sorted(ftype for ftype in ftypes if ftype not in {390, 436})
    return {
        "source_universe": "NHD_WATERBODY_FEATURE",
        "page_count": len(pages),
        "discovered_rows": len(rows),
        "retained_rows": len(retained),
        "excluded_rows": len(rows) - len(retained),
        "ftype_390": ftypes.get(390, 0),
        "ftype_436": ftypes.get(436, 0),
        "duplicate_pid_count": len(duplicates),
        "unexpected_ftypes": unexpected,
        "arithmetic_closure": ftypes.get(390, 0) + ftypes.get(436, 0) == len(retained),
        "schema_fingerprint": schema_fingerprint(rows),
    }


def detect_csv_header(payload: bytes, required_any: Sequence[str]) -> tuple[int, list[str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    required = {item.strip() for item in required_any}
    for index, line in enumerate(lines[:50]):
        fields = next(csv.reader([line]))
        normalized = {field.strip() for field in fields}
        if required & normalized:
            return index, fields
    raise RuntimeError(f"CSV header not found in first 50 lines for {sorted(required)}")


def parse_nid_csv(payload: bytes) -> tuple[list[str], list[dict[str, str]], str]:
    header_index, fields = detect_csv_header(payload, ["NID ID", "NID_ID"])
    text = payload.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    preamble = "\n".join(lines[:header_index])
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    rows = [dict(row) for row in reader]
    return fields, rows, preamble


def certify_nid_csv(payload: bytes) -> dict[str, Any]:
    fields, rows, preamble = parse_nid_csv(payload)
    if not rows:
        raise RuntimeError("NID CSV has no data rows")
    def nid_id(row: Mapping[str, Any]) -> str:
        return str(row.get("NID ID") or row.get("NID_ID") or "").strip()
    def state(row: Mapping[str, Any]) -> str:
        return str(row.get("State") or row.get("STATE") or "").strip()
    prefix = {nid_id(row) for row in rows if nid_id(row).startswith("PR")}
    by_state = {nid_id(row) for row in rows if state(row) == "PR"}
    duplicates = len(prefix) - len(set(prefix))
    return {
        "source_universe": "NID_DAM_ASSET",
        "header_line_index": len(preamble.splitlines()) if preamble else 0,
        "preamble": preamble,
        "column_count": len(fields),
        "national_rows": len(rows),
        "pr_prefix_count": len(prefix),
        "pr_state_count": len(by_state),
        "prefix_state_set_equal": prefix == by_state,
        "duplicate_pr_nid_ids": duplicates,
        "schema_fingerprint": schema_fingerprint(rows),
        "raw_string_preservation": True,
        "matching_normalization_is_separate": True,
    }


def archive_member_manifest(payload: bytes) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        rows = []
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            data = archive.read(member.filename)
            rows.append({
                "path": member.filename,
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "is_dir": member.is_dir(),
            })
        return rows


def certify_inland_bathy_archive(payload: bytes, *, pr_subject_rows: Sequence[Mapping[str, Any]], hard_bindings: Mapping[str, str]) -> dict[str, Any]:
    members = archive_member_manifest(payload)
    if not members:
        raise RuntimeError("Inland Bathymetry archive has no members")
    names = [str(row.get("name") or row.get("Feature") or "") for row in pr_subject_rows]
    normalized = [matching_text(name) for name in names]
    if len(pr_subject_rows) != len(set(normalized)):
        raise RuntimeError("duplicate PR survey subject after matching normalization")
    return {
        "source_universe": "USGS_BATHY_SURVEY_FOOTPRINT",
        "archive_member_count": len(members),
        "archive_member_manifest": members,
        "pr_subject_count": len(pr_subject_rows),
        "hard_binding_count": len(hard_bindings),
        "hard_bindings": {str(k): canonical_pid(v) for k, v in sorted(hard_bindings.items())},
        "schema_fingerprint": schema_fingerprint(pr_subject_rows),
        "raw_names": names,
    }


def logical_certification_fingerprint(document: Mapping[str, Any]) -> str:
    return sha256_bytes(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
