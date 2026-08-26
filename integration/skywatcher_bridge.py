"""SKYWATCHER -> SPIDERWEB BRIDGE CONSUMER (retained integration boundary)

This is the ONLY sanctioned FR24-related integration point Spiderweb retains
after the FR24 screenshot-processing capability moved to skywatcher-pr. It
consumes a hub-canonical Skywatcher export package (a directory containing
``manifest.json`` + ``bridge_records.jsonl`` of ``spiderweb_bridge`` records),
schema-validates every record, and routes the valid ones into Spiderweb's
downstream ``flights`` / ``track_points`` tables so the existing GIS / mission /
operational intelligence can correlate them.

Policy (candidate-only, no auto-confirmation):
  * every record is validated against schemas/spiderweb_bridge.schema.json;
  * records that fail validation are rejected (held), never ingested;
  * defense-in-depth: any record carrying a terminal-accept label (e.g.
    "confirmed") is rejected even if it somehow passed schema validation.

It performs NO screenshot processing, NO OCR, and does not open or migrate the
legacy flight_database.db screenshot tables. It creates only the minimal
flights/track_points tables the downstream consumers read.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
BRIDGE_SCHEMA_PATH = REPO_ROOT / "schemas" / "spiderweb_bridge.schema.json"

# Defense-in-depth: bridge records must never assert a confirmed/verified verdict.
PROHIBITED_LABELS = {
    "confirmed",
    "confirmed_aircraft_event",
    "confirmed_anomaly",
    "confirmed_route",
    "verified_event",
    "validated_aircraft_event",
}

_FLIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS flights (
    flight_id TEXT PRIMARY KEY,
    callsign TEXT,
    aircraft_type TEXT,
    operator TEXT,
    origin_airport TEXT,
    destination_airport TEXT,
    origin_lat REAL, origin_lon REAL, dest_lat REAL, dest_lon REAL,
    takeoff_time TEXT, landing_time TEXT,
    flight_duration_minutes INTEGER,
    max_altitude_ft INTEGER, avg_speed_mph REAL,
    mission_type TEXT, num_screenshots INTEGER,
    review_status TEXT,
    source_adapter TEXT
)
"""

_TRACK_DDL = """
CREATE TABLE IF NOT EXISTS track_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id TEXT,
    timestamp TEXT,
    latitude REAL, longitude REAL,
    altitude_ft INTEGER, ground_speed_mph REAL,
    FOREIGN KEY(flight_id) REFERENCES flights(flight_id)
)
"""

INGEST_ADAPTER_VERSION = "spiderweb_ingest_skywatcher_v0.1.0"


class BridgeValidationError(RuntimeError):
    pass


def load_schema() -> Dict[str, Any]:
    if not BRIDGE_SCHEMA_PATH.is_file():
        raise BridgeValidationError(f"bridge schema missing: {BRIDGE_SCHEMA_PATH}")
    return json.loads(BRIDGE_SCHEMA_PATH.read_text(encoding="utf-8"))


def _iso_ok(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    try:
        from datetime import datetime

        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _datetime_problems(record: Dict[str, Any]) -> List[str]:
    """Deterministic ISO-8601 checks (jsonschema `format` is advisory and needs a
    backing lib, so timing fields are verified explicitly)."""
    problems: List[str] = []
    if not _iso_ok(record.get("generated_at_utc")):
        problems.append("generated_at_utc: not an ISO-8601 datetime")
    interval = record.get("validated_time_interval") or {}
    for k in ("start", "end"):
        if not _iso_ok(interval.get(k)):
            problems.append(f"validated_time_interval.{k}: not an ISO-8601 datetime")
    return problems


def validate_record(record: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return a list of validation errors for one bridge record (empty == valid)."""
    from jsonschema import Draft202012Validator  # lazy: declared dependency

    schema = schema or load_schema()
    # format_checker enables `format` assertions where a backing lib exists;
    # _datetime_problems guarantees date-time enforcement regardless.
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(record)]
    errors += _datetime_problems(record)
    if _has_prohibited_label(record):
        errors.append("prohibited terminal-accept label present")
    return errors


def _has_prohibited_label(record: Dict[str, Any]) -> bool:
    def _scan(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in PROHIBITED_LABELS
        if isinstance(value, dict):
            return any(_scan(v) for v in value.values())
        if isinstance(value, list):
            return any(_scan(v) for v in value)
        return False

    return _scan(record)


def read_package(package_dir: Path) -> List[Dict[str, Any]]:
    """Read bridge records from a hub-canonical package directory.

    Requires the package `manifest.json` and verifies its identity/counts against
    the records — so a hand-assembled or mixed-`export_id` JSONL is rejected
    rather than silently accepted as a canonical Skywatcher package.
    """
    package_dir = Path(package_dir)
    records_path = package_dir / "bridge_records.jsonl"
    manifest_path = package_dir / "manifest.json"
    if not records_path.is_file():
        raise BridgeValidationError(
            f"package missing bridge_records.jsonl: {records_path}. "
            f"Expected a Skywatcher --export-spiderweb package directory."
        )
    if not manifest_path.is_file():
        raise BridgeValidationError(
            f"package missing manifest.json: {manifest_path}. "
            f"A hub-canonical Skywatcher package must include its manifest."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    records: List[Dict[str, Any]] = []
    for line in records_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))

    # Verify the manifest's declared count matches the records present.
    declared = (manifest.get("record_counts") or {}).get("flights")
    if declared is not None and declared != len(records):
        raise BridgeValidationError(
            f"manifest record_counts.flights={declared} != {len(records)} records present"
        )
    # Verify every record belongs to the manifest's package (single export_id).
    manifest_export_id = manifest.get("export_id")
    if manifest_export_id:
        # Only records that declare an export_id are checked here; records
        # missing it fail per-record schema validation downstream.
        stray = {r.get("export_id") for r in records if r.get("export_id")} - {manifest_export_id}
        if stray:
            raise BridgeValidationError(
                f"records carry export_id(s) {sorted(stray)} not matching manifest {manifest_export_id!r}"
            )
    return records


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(_FLIGHTS_DDL)
    conn.execute(_TRACK_DDL)
    conn.commit()


def _ingest_one(conn: sqlite3.Connection, rec: Dict[str, Any]) -> None:
    interval = rec.get("validated_time_interval") or {}
    conn.execute(
        """
        INSERT OR REPLACE INTO flights
            (flight_id, callsign, mission_type, takeoff_time, landing_time,
             review_status, num_screenshots, source_adapter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec["flight_id"],
            rec.get("aircraft_id"),
            (rec.get("mission_classification") or {}).get("value"),
            interval.get("start"),
            interval.get("end"),
            rec.get("review_status"),
            0,
            INGEST_ADAPTER_VERSION,
        ),
    )
    conn.execute("DELETE FROM track_points WHERE flight_id = ?", (rec["flight_id"],))
    geom = rec.get("validated_track_geometry") or {}
    for coord in geom.get("coordinates", []) or []:
        if len(coord) >= 2:
            conn.execute(
                "INSERT INTO track_points (flight_id, longitude, latitude) VALUES (?, ?, ?)",
                (rec["flight_id"], coord[0], coord[1]),
            )


def ingest_package(
    package_dir: Path,
    db_path: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Validate and (unless dry_run) ingest a Skywatcher bridge package.

    Returns a summary: total / ingested / rejected + per-reject reasons.
    Ingestion is transactional; any invalid record is held (not ingested).
    """
    records = read_package(package_dir)
    schema = load_schema()

    valid: List[Dict[str, Any]] = []
    rejects: List[Dict[str, Any]] = []
    for rec in records:
        errors = validate_record(rec, schema)
        if errors:
            rejects.append({"flight_id": rec.get("flight_id"), "errors": errors})
        else:
            valid.append(rec)

    ingested = 0
    if not dry_run and valid:
        conn = sqlite3.connect(db_path)
        try:
            _ensure_tables(conn)
            for rec in valid:
                _ingest_one(conn, rec)
            conn.commit()
            ingested = len(valid)
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    return {
        "package": str(package_dir),
        "total": len(records),
        "valid": len(valid),
        "ingested": ingested,
        "rejected": len(rejects),
        "rejects": rejects,
        "dry_run": dry_run,
        "adapter_version": INGEST_ADAPTER_VERSION,
    }
