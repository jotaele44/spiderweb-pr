"""
SCHEMA VALIDATION
Validates records against JSON schemas and routes invalid rows to review_queue.csv.
"""

import csv
import json
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
REVIEW_QUEUE_FIELDNAMES = ["schema_name", "record_json", "errors", "routed_at"]


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
    ) -> Tuple[List[dict], int]:
        """
        Validate every record in records against schema_name.
        Invalid records are appended to review_queue_path (CSV, created if missing).
        Returns (valid_records, n_invalid).
        """
        valid_records = []
        invalid_count = 0

        for record in records:
            result = self.validate(record, schema_name)
            if result["valid"]:
                valid_records.append(record)
            else:
                invalid_count += 1
                self._write_review_item(
                    review_queue_path,
                    schema_name=schema_name,
                    record=record,
                    errors=result["errors"],
                )

        return valid_records, invalid_count

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

    def _write_review_item(self, path: str, schema_name: str,
                           record: dict, errors: List[str]):
        file_exists = Path(path).exists()
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REVIEW_QUEUE_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "schema_name": schema_name,
                "record_json": json.dumps(record, default=str),
                "errors":      "; ".join(errors),
                "routed_at":   datetime.utcnow().isoformat() + "Z",
            })

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
                    rows, schema_name, review_queue_path
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
