"""
SCHEMA VALIDATION
Validates records against JSON schemas and routes invalid rows to review_queue.csv.
"""

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema
    from jsonschema import Draft7Validator
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

# Enriched review-queue contract: one row per (record, validation error).
REVIEW_QUEUE_FIELDNAMES = [
    "routed_at", "record_id", "source_file", "schema_name",
    "field", "error_type", "error_message", "record_json", "suggested_fix",
]

# Candidate identifier keys, in priority order, for review-queue traceability.
_ID_KEYS = ("flight_id", "screenshot_id", "id", "alert_id", "candidate_id", "manifest_id")

# error_type (jsonschema validator keyword) → operator-facing remediation hint.
_FIX_HINTS = {
    "required": "add the missing required field",
    "type": "correct the value type",
    "enum": "use an allowed enum value",
    "format": "fix the value format",
    "pattern": "match the required pattern",
    "minimum": "increase the value to meet the minimum",
    "maximum": "decrease the value to meet the maximum",
    "minLength": "provide a longer value",
    "maxLength": "shorten the value",
}


def _extract_record_id(record: dict) -> str:
    """First non-empty identifier among _ID_KEYS, else ''."""
    for k in _ID_KEYS:
        v = record.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _suggest_fix(error_type: str) -> str:
    return _FIX_HINTS.get(error_type, "")


def _within_window(ts: Optional[str], cutoff_ts: float) -> bool:
    """True if ISO-8601 *ts* (optionally Z-suffixed) is at or after *cutoff_ts*."""
    if not ts:
        return False
    try:
        return datetime.fromisoformat(ts.replace("Z", "")).timestamp() >= cutoff_ts
    except Exception:
        return False


class SchemaValidator:
    """
    Loads JSON schemas from the schemas/ directory and validates records.
    Routes invalid records to review_queue.csv.

    Falls back to no-op (all valid) if jsonschema is not installed.
    """

    def __init__(self, schemas_dir: Optional[str] = None):
        self._dir = Path(schemas_dir) if schemas_dir else SCHEMAS_DIR
        self._validators: Dict[str, Any] = {}
        if _JSONSCHEMA_AVAILABLE:
            self._load_schemas()

    def _load_schemas(self):
        if not self._dir.exists():
            return
        for path in self._dir.glob("*.schema.json"):
            name = path.stem.replace(".schema", "")
            try:
                with open(path) as f:
                    schema = json.load(f)
                self._validators[name] = Draft7Validator(schema)
            except Exception:
                pass

    def validate(self, record: dict, schema_name: str) -> Dict[str, Any]:
        """
        Validate a single record. Returns {"valid": bool, "errors": list[str]}.
        If jsonschema is unavailable or schema not found, returns valid=True.
        """
        if not _JSONSCHEMA_AVAILABLE or schema_name not in self._validators:
            return {"valid": True, "errors": []}

        validator = self._validators[schema_name]
        errors = [e.message for e in validator.iter_errors(record)]
        return {"valid": len(errors) == 0, "errors": errors}

    def validate_batch(
        self,
        records: List[dict],
        schema_name: str,
        review_queue_path: str,
        source_file: str = "",
    ) -> Tuple[List[dict], int]:
        """
        Validate every record in records against schema_name.

        Invalid records are routed to review_queue_path as ONE ROW PER
        (record, validation error) with structured columns (see
        REVIEW_QUEUE_FIELDNAMES). Rows are deduplicated on
        (schema_name, record_id, field, error_type) within a 24h window and the
        file is rewritten atomically. Returns (valid_records, n_invalid) where
        n_invalid counts invalid *records* (not rows).
        """
        valid_records: List[dict] = []
        invalid_count = 0
        review_rows: List[dict] = []

        for record in records:
            errors = self._structured_errors(record, schema_name)
            if not errors:
                valid_records.append(record)
                continue
            invalid_count += 1
            record_id = _extract_record_id(record)
            record_json = json.dumps(record, default=str)
            routed_at = datetime.utcnow().isoformat() + "Z"
            for err in errors:
                review_rows.append({
                    "routed_at": routed_at,
                    "record_id": record_id,
                    "source_file": source_file,
                    "schema_name": schema_name,
                    "field": err["field"],
                    "error_type": err["error_type"],
                    "error_message": err["error_message"],
                    "record_json": record_json,
                    "suggested_fix": _suggest_fix(err["error_type"]),
                })

        if review_rows:
            self._append_review_rows(review_queue_path, review_rows)

        return valid_records, invalid_count

    def _structured_errors(self, record: dict, schema_name: str) -> List[Dict[str, str]]:
        """Return [{field, error_type, error_message}, ...] for *record*. Empty
        when valid, jsonschema unavailable, or schema unknown (matches validate())."""
        if not _JSONSCHEMA_AVAILABLE or schema_name not in self._validators:
            return []
        out: List[Dict[str, str]] = []
        for e in self._validators[schema_name].iter_errors(record):
            field = ".".join(str(p) for p in e.absolute_path) or "<root>"
            out.append({
                "field": field,
                "error_type": getattr(e, "validator", "") or "",
                "error_message": e.message,
            })
        return out

    def validate_export_manifest(self, manifest: dict) -> Dict[str, Any]:
        return self.validate(manifest, "export_manifest")

    def available_schemas(self) -> List[str]:
        return list(self._validators.keys())

    def reload_schemas(self) -> int:
        """Discard cached validators and reload from disk. Returns count loaded."""
        self._validators = {}
        if _JSONSCHEMA_AVAILABLE:
            self._load_schemas()
        return len(self._validators)

    def schema_count(self) -> int:
        """Return the number of currently loaded schemas."""
        return len(self._validators)

    def validate_with_context(
        self, record: dict, schema_name: str, context: str
    ) -> Dict[str, Any]:
        """Validate *record* and prefix each error message with *context*."""
        result = self.validate(record, schema_name)
        if not result["valid"]:
            result["errors"] = [f"[{context}] {e}" for e in result["errors"]]
        return result

    def get_schema_names(self) -> List[str]:
        """Return a sorted list of loaded schema names."""
        return sorted(self._validators.keys())

    def _append_review_rows(self, path: str, new_rows: List[dict],
                            dedup_window_hours: float = 24.0) -> None:
        """Merge *new_rows* into the review queue at *path*, deduplicating on
        (schema_name, record_id, field, error_type) within *dedup_window_hours*,
        and rewrite atomically (tmpfile → os.replace). Legacy rows missing the
        key columns are preserved but not used for dedup."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        existing: List[dict] = []
        if p.exists():
            try:
                with open(p, newline="") as f:
                    existing = list(csv.DictReader(f))
            except Exception:
                existing = []

        cutoff = datetime.utcnow().timestamp() - dedup_window_hours * 3600.0
        recent_keys = set()
        for r in existing:
            key = (r.get("schema_name"), r.get("record_id"),
                   r.get("field"), r.get("error_type"))
            if None in key:
                continue  # legacy row without the new key columns
            if _within_window(r.get("routed_at"), cutoff):
                recent_keys.add(key)

        deduped: List[dict] = []
        seen_new = set()
        for r in new_rows:
            key = (r["schema_name"], r["record_id"], r["field"], r["error_type"])
            if key in recent_keys or key in seen_new:
                continue
            seen_new.add(key)
            deduped.append(r)

        combined = existing + deduped
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=REVIEW_QUEUE_FIELDNAMES,
                                        extrasaction="ignore")
                writer.writeheader()
                for r in combined:
                    writer.writerow({k: r.get(k, "") for k in REVIEW_QUEUE_FIELDNAMES})
            os.replace(tmp, str(p))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def run_db_validation(
        self,
        db_path: str,
        review_queue_path: str,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Validate key tables from a flight database.
        Returns per-table summary {"schema_name": {"valid": N, "invalid": N}}.
        """
        import sqlite3

        TABLE_SCHEMA_MAP = {
            "flights":              "flight_event",
            "screenshots":          "screenshot",
            "track_points":         "track_point",
            "extraction_confidence":"extracted_field",
            "alerts":               "anomaly",
            "mission_scores":       "mission_inference",
        }

        results = {}
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            for table, schema_name in TABLE_SCHEMA_MAP.items():
                try:
                    rows = [dict(r) for r in conn.execute(
                        f"SELECT * FROM {table} LIMIT 5000"
                    )]
                except Exception:
                    continue

                valid_rows, n_invalid = self.validate_batch(
                    rows, schema_name, review_queue_path,
                    source_file=f"{db_path}:{table}",
                )
                results[schema_name] = {
                    "table": table,
                    "total": len(rows),
                    "valid": len(valid_rows),
                    "invalid": n_invalid,
                }
            conn.close()
        except Exception as e:
            results["_error"] = {"error": str(e)}

        return results
