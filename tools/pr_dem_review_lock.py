#!/usr/bin/env python3
"""Validate, merge, summarize, and lock PR DEM candidate manual reviews.

Inputs
------
- Candidate GeoJSON from the one-tile or batch DEM pilot.
- Manual review CSV using templates/pr_dem_candidate_manual_review_template.csv.
- JSON schema at schemas/pr_dem_candidate_review.schema.json.

Outputs
-------
- validation_report.json
- validation_findings.csv
- invalid_review_rows.csv
- reviewed_candidates.geojson
- review_summary.json
- review_summary.md
- locked_review_manifest.json

No candidate is converted into a confirmed finding by this tool. It preserves
manual review decisions as review metadata and keeps the original candidate
geometry/properties intact.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


NULL_STRINGS = {"", "null", "none", "na", "n/a", "nan"}


class ValidationError(Exception):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_null(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in NULL_STRINGS:
        return None
    return value


def coerce_value(value: Any, schema: Dict[str, Any], field: str, row_number: int) -> Any:
    value = normalize_null(value)
    allowed_type = schema.get("type")
    allowed_types = allowed_type if isinstance(allowed_type, list) else [allowed_type]

    if value is None:
        return None

    if "number" in allowed_types:
        try:
            return float(value)
        except Exception as exc:
            raise ValidationError(f"row {row_number}: field {field} must be numeric; got {value!r}") from exc

    if "integer" in allowed_types:
        try:
            return int(value)
        except Exception as exc:
            raise ValidationError(f"row {row_number}: field {field} must be integer; got {value!r}") from exc

    if "boolean" in allowed_types:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n"}:
            return False
        raise ValidationError(f"row {row_number}: field {field} must be boolean; got {value!r}")

    return str(value).strip()


def validate_format(value: Any, fmt: Optional[str], field: str, row_number: int) -> None:
    if value is None or not fmt:
        return
    if fmt == "date-time":
        text = str(value)
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt.datetime.fromisoformat(text)
        except Exception as exc:
            raise ValidationError(f"row {row_number}: field {field} must be ISO date-time; got {value!r}") from exc


def validate_bounds(value: Any, field_schema: Dict[str, Any], field: str, row_number: int) -> None:
    if value is None or not isinstance(value, (int, float)):
        return
    if "minimum" in field_schema and value < field_schema["minimum"]:
        raise ValidationError(f"row {row_number}: field {field} below minimum {field_schema['minimum']}; got {value}")
    if "maximum" in field_schema and value > field_schema["maximum"]:
        raise ValidationError(f"row {row_number}: field {field} above maximum {field_schema['maximum']}; got {value}")


def validate_enum(value: Any, field_schema: Dict[str, Any], field: str, row_number: int) -> None:
    if "enum" not in field_schema:
        return
    allowed = field_schema["enum"]
    if value not in allowed:
        raise ValidationError(f"row {row_number}: field {field} value {value!r} not in allowed enum {allowed}")


def validate_record(row: Dict[str, Any], schema: Dict[str, Any], row_number: int) -> Tuple[Dict[str, Any], List[str]]:
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional_allowed = schema.get("additionalProperties", True)
    output: Dict[str, Any] = {}
    warnings: List[str] = []

    for field in required:
        if normalize_null(row.get(field)) is None:
            raise ValidationError(f"row {row_number}: missing required field {field}")

    if not additional_allowed:
        extra = sorted(set(row) - set(properties))
        extra = [x for x in extra if x and normalize_null(row.get(x)) is not None]
        if extra:
            warnings.append(f"row {row_number}: extra fields ignored: {extra}")

    for field, field_schema in properties.items():
        raw = row.get(field)
        value = coerce_value(raw, field_schema, field, row_number)
        validate_enum(value, field_schema, field, row_number)
        validate_bounds(value, field_schema, field, row_number)
        validate_format(value, field_schema.get("format"), field, row_number)
        output[field] = value

    return output, warnings


def load_review_csv(path: Path, schema: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    valid_rows: List[Dict[str, Any]] = []
    invalid_rows: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    warnings: List[str] = []

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"Review CSV has no header: {path}")
        for row_number, row in enumerate(reader, start=2):
            if not any(normalize_null(v) is not None for v in row.values()):
                continue
            try:
                record, row_warnings = validate_record(row, schema, row_number)
                valid_rows.append(record)
                for warning in row_warnings:
                    warnings.append(warning)
                    findings.append({"severity": "WARN", "row_number": row_number, "candidate_id": row.get("candidate_id", ""), "message": warning})
            except ValidationError as exc:
                invalid = dict(row)
                invalid["_row_number"] = row_number
                invalid["_validation_error"] = str(exc)
                invalid_rows.append(invalid)
                findings.append({"severity": "FAIL", "row_number": row_number, "candidate_id": row.get("candidate_id", ""), "message": str(exc)})

    duplicate_ids = [cid for cid, count in Counter(str(r.get("candidate_id")) for r in valid_rows).items() if count > 1]
    for cid in duplicate_ids:
        findings.append({"severity": "FAIL", "row_number": "", "candidate_id": cid, "message": "duplicate candidate_id in valid review rows"})

    if duplicate_ids:
        invalid_rows.append({"_row_number": "", "candidate_id": ";".join(duplicate_ids), "_validation_error": "duplicate candidate_id values"})

    return valid_rows, invalid_rows, findings, warnings


def write_findings_csv(path: Path, findings: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["severity", "row_number", "candidate_id", "message"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in findings:
            writer.writerow({key: item.get(key, "") for key in fieldnames})


def write_invalid_rows(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    if not fieldnames:
        fieldnames = ["_row_number", "candidate_id", "_validation_error"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_candidate_geojson(path: Path) -> Dict[str, Any]:
    payload = load_json(path)
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Candidate GeoJSON must be a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise SystemExit("Candidate GeoJSON missing features list")
    return payload


def index_features_by_candidate_id(geojson: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        candidate_id = props.get("candidate_id")
        if candidate_id:
            index[str(candidate_id)] = feature
    return index


def review_prefixed(record: Dict[str, Any]) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    for key, value in record.items():
        if key == "candidate_id":
            continue
        output[f"review_{key}"] = value
    return output


def merge_reviews(candidate_geojson: Dict[str, Any], review_rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    feature_index = index_features_by_candidate_id(candidate_geojson)
    review_index = {str(row["candidate_id"]): row for row in review_rows}
    matched = sorted(set(feature_index) & set(review_index))
    unmatched_reviews = sorted(set(review_index) - set(feature_index))
    unreviewed_candidates = sorted(set(feature_index) - set(review_index))

    for cid in matched:
        feature = feature_index[cid]
        props = feature.setdefault("properties", {})
        props.update(review_prefixed(review_index[cid]))
        props["review_merge_status"] = "review_attached"

    for cid in unreviewed_candidates:
        feature = feature_index[cid]
        props = feature.setdefault("properties", {})
        props.setdefault("review_merge_status", "no_review_row")

    output = dict(candidate_geojson)
    output["generated_at_utc"] = utc_now()
    output["review_merge_status"] = {
        "matched_review_count": len(matched),
        "unmatched_review_count": len(unmatched_reviews),
        "unreviewed_candidate_count": len(unreviewed_candidates),
    }

    merge_stats = {
        "candidate_feature_count": len(feature_index),
        "review_row_count": len(review_rows),
        "matched_review_count": len(matched),
        "unmatched_review_ids": unmatched_reviews,
        "unreviewed_candidate_count": len(unreviewed_candidates),
    }
    return output, merge_stats


def summarize(review_rows: Sequence[Dict[str, Any]], merge_stats: Dict[str, Any], validation_status: str) -> Dict[str, Any]:
    counts: Dict[str, Dict[str, int]] = {}
    for field in [
        "review_status",
        "review_decision",
        "review_confidence",
        "recommended_next_step",
        "terrain_visual_type",
        "access_context",
        "hydro_context",
        "utility_context",
        "karst_context",
        "imagery_context",
        "evidence_tier",
    ]:
        counts[field] = dict(Counter(str(row.get(field)) for row in review_rows if row.get(field) is not None))

    score_values = [row.get("ILAP_SCORE") for row in review_rows if isinstance(row.get("ILAP_SCORE"), (int, float))]
    score_summary = {
        "count": len(score_values),
        "min": min(score_values) if score_values else None,
        "max": max(score_values) if score_values else None,
        "mean": round(sum(score_values) / len(score_values), 3) if score_values else None,
    }

    return {
        "generated_at_utc": utc_now(),
        "validation_status": validation_status,
        "review_row_count": len(review_rows),
        "merge_stats": merge_stats,
        "counts": counts,
        "score_summary": score_summary,
        "guardrail": "Manual review records are prioritization metadata only and do not confirm hidden infrastructure or subsurface activity.",
    }


def write_summary_md(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# PR DEM Candidate Review Summary")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_at_utc']}`")
    lines.append("")
    lines.append(f"Validation status: `{summary['validation_status']}`")
    lines.append(f"Review rows: `{summary['review_row_count']}`")
    lines.append("")
    lines.append("## Merge stats")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for key, value in summary["merge_stats"].items():
        if isinstance(value, list):
            value = len(value)
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## Score summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for key, value in summary["score_summary"].items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## Review decision counts")
    lines.append("")
    for field, counts in summary["counts"].items():
        lines.append(f"### {field}")
        lines.append("")
        lines.append("| Value | Count |")
        lines.append("|---|---:|")
        if counts:
            for value, count in sorted(counts.items()):
                lines.append(f"| {value} | {count} |")
        else:
            lines.append("| none | 0 |")
        lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append(summary["guardrail"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def copy_if_requested(paths: Sequence[Path], lock_dir: Optional[Path]) -> List[Dict[str, Any]]:
    locked: List[Dict[str, Any]] = []
    if lock_dir:
        lock_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        final_path = path
        if lock_dir:
            final_path = lock_dir / path.name
            shutil.copy2(path, final_path)
        locked.append({
            "name": final_path.name,
            "path": str(final_path),
            "size_bytes": final_path.stat().st_size,
            "sha256": sha256_file(final_path),
        })
    return locked


def write_lock_manifest(path: Path, inputs: Dict[str, Path], output_files: Sequence[Path], lock_dir: Optional[Path], validation_status: str, merge_stats: Dict[str, Any]) -> None:
    locked_outputs = copy_if_requested(output_files, lock_dir)
    payload = {
        "generated_at_utc": utc_now(),
        "tool": "tools/pr_dem_review_lock.py",
        "validation_status": validation_status,
        "merge_stats": merge_stats,
        "inputs": {
            key: {
                "path": str(value),
                "size_bytes": value.stat().st_size if value.exists() else None,
                "sha256": sha256_file(value) if value.exists() else None,
            }
            for key, value in inputs.items()
        },
        "locked_outputs": locked_outputs,
        "lock_dir": str(lock_dir) if lock_dir else None,
    }
    write_json(path, payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate manual review CSV, merge review fields into GeoJSON, and emit locked review artifacts.")
    p.add_argument("--candidate-geojson", required=True, help="Candidate GeoJSON from one-tile or batch DEM output.")
    p.add_argument("--review-csv", required=True, help="Manual review CSV using the PR DEM candidate review template.")
    p.add_argument("--schema", default="schemas/pr_dem_candidate_review.schema.json", help="Review JSON schema path.")
    p.add_argument("--output-dir", default="outputs/pr_dem_review_lock", help="Output directory for reviewed artifacts.")
    p.add_argument("--lock-dir", default="", help="Optional copy output directory for locked artifacts.")
    p.add_argument("--allow-invalid", action="store_true", help="Continue merge even if invalid review rows exist. Invalid rows are excluded.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    candidate_geojson_path = Path(args.candidate_geojson).expanduser().resolve()
    review_csv_path = Path(args.review_csv).expanduser().resolve()
    schema_path = Path(args.schema).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    lock_dir = Path(args.lock_dir).expanduser().resolve() if args.lock_dir else None
    output_dir.mkdir(parents=True, exist_ok=True)

    for label, path in {"candidate_geojson": candidate_geojson_path, "review_csv": review_csv_path, "schema": schema_path}.items():
        if not path.exists() or path.stat().st_size == 0:
            raise SystemExit(f"Missing or empty {label}: {path}")

    schema = load_json(schema_path)
    review_rows, invalid_rows, findings, warnings = load_review_csv(review_csv_path, schema)
    fail_count = sum(1 for item in findings if item.get("severity") == "FAIL")
    validation_status = "PASS" if fail_count == 0 else "FAIL"

    validation_report = {
        "generated_at_utc": utc_now(),
        "status": validation_status,
        "valid_review_rows": len(review_rows),
        "invalid_review_rows": len(invalid_rows),
        "finding_count": len(findings),
        "fail_count": fail_count,
        "warnings": warnings,
    }
    write_json(output_dir / "validation_report.json", validation_report)
    write_findings_csv(output_dir / "validation_findings.csv", findings)
    write_invalid_rows(output_dir / "invalid_review_rows.csv", invalid_rows)

    if validation_status == "FAIL" and not args.allow_invalid:
        print(json.dumps(validation_report, indent=2))
        print(f"Invalid rows written to: {output_dir / 'invalid_review_rows.csv'}")
        print("Use --allow-invalid only if you want to exclude invalid rows and continue merging valid rows.")
        return 2

    candidate_geojson = load_candidate_geojson(candidate_geojson_path)
    reviewed_geojson, merge_stats = merge_reviews(candidate_geojson, review_rows)
    reviewed_geojson_path = output_dir / "reviewed_candidates.geojson"
    write_json(reviewed_geojson_path, reviewed_geojson)

    summary = summarize(review_rows, merge_stats, validation_status)
    summary_json_path = output_dir / "review_summary.json"
    summary_md_path = output_dir / "review_summary.md"
    write_json(summary_json_path, summary)
    write_summary_md(summary_md_path, summary)

    output_files = [
        reviewed_geojson_path,
        summary_json_path,
        summary_md_path,
        output_dir / "validation_report.json",
        output_dir / "validation_findings.csv",
        output_dir / "invalid_review_rows.csv",
    ]
    write_lock_manifest(
        output_dir / "locked_review_manifest.json",
        inputs={"candidate_geojson": candidate_geojson_path, "review_csv": review_csv_path, "schema": schema_path},
        output_files=output_files,
        lock_dir=lock_dir,
        validation_status=validation_status,
        merge_stats=merge_stats,
    )

    print(f"Validation status: {validation_status}")
    print(f"Valid review rows: {len(review_rows)}")
    print(f"Invalid review rows: {len(invalid_rows)}")
    print(f"Reviewed GeoJSON: {reviewed_geojson_path}")
    print(f"Summary: {summary_md_path}")
    print(f"Lock manifest: {output_dir / 'locked_review_manifest.json'}")
    return 0 if validation_status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
