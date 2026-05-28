"""
Spiderweb federation export package validator.

Validates a producer's export package against the federation contract:
  - manifest shape (spiderweb_airspace_export.schema.json)
  - per-stream row shape (events, observations, tracks, sources)
  - declared sha256 / record_count integrity
  - deterministic id integrity (spot-check)
  - required-field gates: source_id, lineage, confidence, timestamp
  - geometry coordinate ranges
  - ISO-8601 timezone-aware timestamps
  - production mode rejects rows with is_synthetic: true

Exit codes:
  0  package is valid for the requested mode
  2  package failed validation (validation_report.json written next to package)
  3  package layout is broken (missing manifest, unreadable file)
  4  invalid CLI arguments

Usage:
    python scripts/validate_export.py --package <dir> --mode {test,production}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft7Validator
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(4)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"

MANIFEST_SCHEMA_ID = "spiderweb_airspace_export"

STREAM_SCHEMA = {
    "events":       "spiderweb_event",
    "observations": "spiderweb_observation",
    "tracks":       "spiderweb_track",
    "sources":      "spiderweb_source",
}

STREAM_TIME_FIELD = {
    "events":       "event_time",
    "observations": "observed_at",
    "tracks":       "observed_at",
    "sources":      "first_seen_at",
}


def compute_row_id(row: dict[str, Any]) -> str:
    """Deterministic row id: sha256 over canonical JSON of the row sans 'id'.

    Truncated to 32 lowercase hex chars. The canonical form uses sorted keys
    and no whitespace, so identical payloads always hash identically.
    """
    payload = {k: v for k, v in row.items() if k != "id"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def compute_package_id(manifest: dict[str, Any]) -> str:
    """Deterministic package id: sha256 over canonical manifest body sans 'package_id'."""
    body = {k: v for k, v in manifest.items() if k != "package_id"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_tz_aware_iso8601(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    try:
        # fromisoformat handles +HH:MM and (3.11+) trailing 'Z'
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt.tzinfo is not None


def _coord_in_range(lon: Any, lat: Any) -> bool:
    return (
        isinstance(lon, (int, float))
        and isinstance(lat, (int, float))
        and -180 <= lon <= 180
        and -90 <= lat <= 90
    )


def validate_geometry(geom: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(geom, dict):
        return ["geometry is not an object"]
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Point":
        if not (isinstance(coords, list) and len(coords) >= 2):
            errors.append("Point coordinates must be [lon, lat]")
        elif not _coord_in_range(coords[0], coords[1]):
            errors.append(f"Point coordinates out of range: {coords[:2]}")
    elif gtype == "LineString":
        if not (isinstance(coords, list) and len(coords) >= 2):
            errors.append("LineString needs at least 2 coordinate pairs")
        else:
            for i, c in enumerate(coords):
                if not (isinstance(c, list) and len(c) >= 2 and _coord_in_range(c[0], c[1])):
                    errors.append(f"LineString coord[{i}] out of range or malformed")
                    break
    elif gtype == "Polygon":
        if not (isinstance(coords, list) and len(coords) >= 1):
            errors.append("Polygon needs at least 1 ring")
        else:
            for ri, ring in enumerate(coords):
                if not (isinstance(ring, list) and len(ring) >= 4):
                    errors.append(f"Polygon ring {ri} needs at least 4 coords")
                    break
                for i, c in enumerate(ring):
                    if not (isinstance(c, list) and len(c) >= 2 and _coord_in_range(c[0], c[1])):
                        errors.append(f"Polygon ring {ri} coord[{i}] out of range")
                        break
    else:
        errors.append(f"geometry.type must be Point | LineString | Polygon, got {gtype!r}")
    return errors


def _load_schema(schema_id: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / f"{schema_id}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"schema not found: {path}")
    with open(path) as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name}:{lineno} invalid JSON: {e}") from e
    return rows


def _validate_row_gates(row: dict[str, Any], stream: str, mode: str) -> list[str]:
    """Validator-level gates that go beyond the schema."""
    errors: list[str] = []

    if "source_id" not in row or not row["source_id"]:
        errors.append("missing source_id")

    if "lineage" not in row or not isinstance(row["lineage"], list) or len(row["lineage"]) == 0:
        errors.append("missing or empty lineage")

    conf = row.get("confidence")
    if not isinstance(conf, dict) or "score" not in conf or "method" not in conf:
        errors.append("missing or malformed confidence")

    time_field = STREAM_TIME_FIELD[stream]
    if not is_tz_aware_iso8601(row.get(time_field)):
        errors.append(f"missing or non-tz-aware {time_field}")

    if stream == "sources":
        if not is_tz_aware_iso8601(row.get("last_seen_at")):
            errors.append("missing or non-tz-aware last_seen_at")
    elif stream == "tracks":
        errors.extend(validate_geometry(row.get("path")))
    else:
        errors.extend(validate_geometry(row.get("geometry")))

    expected_id = compute_row_id(row)
    if row.get("id") != expected_id:
        errors.append(f"non-deterministic id: stored={row.get('id')!r} expected={expected_id!r}")

    if mode == "production" and row.get("is_synthetic") is True:
        errors.append("synthetic row not allowed in production mode")

    return errors


def validate_package(package_dir: Path, mode: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "package_dir": str(package_dir),
        "mode": mode,
        "status": "ok",
        "errors": [],
        "files": [],
    }

    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        # Allow manifest.sample.json when pointed at a samples dir.
        alt = package_dir / "manifest.sample.json"
        if alt.exists():
            manifest_path = alt
        else:
            report["status"] = "broken"
            report["errors"].append(f"manifest not found at {manifest_path}")
            return report

    with open(manifest_path) as f:
        manifest = json.load(f)

    manifest_schema = _load_schema(MANIFEST_SCHEMA_ID)
    schema_errors = sorted(
        Draft7Validator(manifest_schema).iter_errors(manifest),
        key=lambda e: list(e.path),
    )
    for e in schema_errors:
        report["errors"].append(f"manifest schema: {'/'.join(map(str, e.path)) or '<root>'}: {e.message}")

    expected_pkg = compute_package_id(manifest)
    if manifest.get("package_id") != expected_pkg:
        report["errors"].append(
            f"manifest package_id mismatch: stored={manifest.get('package_id')!r} expected={expected_pkg!r}"
        )

    if not is_tz_aware_iso8601(manifest.get("generated_at")):
        report["errors"].append("manifest.generated_at must be ISO-8601 with timezone")
    tr = manifest.get("time_range") or {}
    for k in ("start", "end"):
        if not is_tz_aware_iso8601(tr.get(k)):
            report["errors"].append(f"manifest.time_range.{k} must be ISO-8601 with timezone")

    seen_streams: set[str] = set()
    for entry in manifest.get("files", []):
        stream = entry.get("stream")
        filename = entry.get("filename")
        declared_sha = entry.get("sha256")
        declared_count = entry.get("record_count")
        schema_id = entry.get("schema_id")

        file_report: dict[str, Any] = {
            "filename": filename,
            "stream": stream,
            "row_errors": [],
        }

        if stream in seen_streams:
            report["errors"].append(f"duplicate stream in manifest: {stream}")
        seen_streams.add(stream)

        if stream not in STREAM_SCHEMA:
            report["errors"].append(f"unknown stream {stream!r}")
            report["files"].append(file_report)
            continue

        if schema_id != STREAM_SCHEMA[stream]:
            report["errors"].append(
                f"{filename}: schema_id mismatch (expected {STREAM_SCHEMA[stream]}, got {schema_id})"
            )

        file_path = package_dir / filename
        if not file_path.exists():
            report["errors"].append(f"declared file not present: {file_path}")
            report["files"].append(file_report)
            continue

        actual_sha = sha256_file(file_path)
        if actual_sha != declared_sha:
            report["errors"].append(
                f"{filename}: sha256 mismatch declared={declared_sha} actual={actual_sha}"
            )

        try:
            rows = _read_jsonl(file_path)
        except ValueError as e:
            report["errors"].append(str(e))
            report["files"].append(file_report)
            continue

        if len(rows) != declared_count:
            report["errors"].append(
                f"{filename}: record_count mismatch declared={declared_count} actual={len(rows)}"
            )

        stream_schema = _load_schema(STREAM_SCHEMA[stream])
        validator = Draft7Validator(stream_schema)
        for i, row in enumerate(rows):
            row_errs: list[str] = []
            for se in sorted(validator.iter_errors(row), key=lambda e: list(e.path)):
                row_errs.append(f"schema: {'/'.join(map(str, se.path)) or '<root>'}: {se.message}")
            row_errs.extend(_validate_row_gates(row, stream, mode))
            if row_errs:
                file_report["row_errors"].append({"row_index": i, "id": row.get("id"), "errors": row_errs})

        report["files"].append(file_report)

    for stream in STREAM_SCHEMA:
        if stream not in seen_streams:
            report["errors"].append(f"manifest missing required stream: {stream}")

    has_row_errors = any(fr["row_errors"] for fr in report["files"])
    if report["errors"] or has_row_errors:
        report["status"] = "failed"

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a spiderweb federation export package.")
    parser.add_argument("--package", required=True, help="Path to package directory containing manifest.json")
    parser.add_argument("--mode", required=True, choices=["test", "production"])
    args = parser.parse_args(argv)

    package_dir = Path(args.package).resolve()
    if not package_dir.is_dir():
        print(f"ERROR: --package must be a directory, got {package_dir}", file=sys.stderr)
        return 3

    report = validate_package(package_dir, args.mode)
    report_path = package_dir / "validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    if report["status"] == "ok":
        print(f"OK: {package_dir} (mode={args.mode})")
        return 0
    if report["status"] == "broken":
        print(f"BROKEN: {package_dir}", file=sys.stderr)
        for e in report["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 3

    print(f"FAILED: {package_dir} (mode={args.mode})", file=sys.stderr)
    for e in report["errors"]:
        print(f"  - {e}", file=sys.stderr)
    for fr in report["files"]:
        for re_ in fr["row_errors"]:
            for msg in re_["errors"]:
                print(f"  - {fr['filename']} row {re_['row_index']} ({re_['id']}): {msg}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
