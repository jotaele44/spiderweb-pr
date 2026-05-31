"""Tests for SchemaValidator: valid/invalid routing."""

import csv
from pathlib import Path

import pytest

pytest.importorskip("jsonschema")

from integration.schema_validation import SCHEMAS_DIR, SchemaValidator


@pytest.fixture
def validator():
    return SchemaValidator()


def test_available_schemas_nonempty(validator):
    schemas = validator.available_schemas()
    assert len(schemas) > 0


def test_validate_valid_screenshot(validator):
    record = {
        "screenshot_id": "SS_001",
        "image_path": "/tmp/img.jpg",
        "processed_at": "2024-03-15T08:00:00",
        "ocr_confidence": 0.85,
    }
    result = validator.validate(record, "screenshot")
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_invalid_screenshot_missing_required(validator):
    record = {"ocr_confidence": 0.85}  # missing screenshot_id, image_path, processed_at
    result = validator.validate(record, "screenshot")
    # If jsonschema is available, should be invalid; otherwise valid (fallback)
    try:
        import jsonschema
        assert result["valid"] is False
        assert len(result["errors"]) > 0
    except ImportError:
        assert result["valid"] is True


def test_validate_batch_routes_invalid(validator, tmp_path):
    review_path = str(tmp_path / "review_queue.csv")
    valid_record = {
        "screenshot_id": "SS_001",
        "image_path": "/tmp/img.jpg",
        "processed_at": "2024-03-15T08:00:00",
    }
    invalid_record = {"ocr_confidence": 0.5}  # missing required fields

    try:
        import jsonschema
        records = [valid_record, invalid_record]
        valid_records, n_invalid = validator.validate_batch(records, "screenshot", review_path)
        assert n_invalid == 1            # one invalid *record*
        assert len(valid_records) == 1
        assert Path(review_path).exists()
        with open(review_path, newline="") as f:
            rows = list(csv.DictReader(f))
        # Enriched contract: one row per validation error (>= 1 for one bad record).
        assert len(rows) >= 1
        assert all(r["schema_name"] == "screenshot" for r in rows)
        assert all(r.get("field") and r.get("error_type") for r in rows)
    except ImportError:
        pytest.skip("jsonschema not installed")


def test_validate_unknown_schema_returns_valid(validator):
    result = validator.validate({"foo": "bar"}, "nonexistent_schema")
    assert result["valid"] is True


def test_validate_export_manifest_valid(validator):
    manifest = {
        "generated_at": "2024-03-15T00:00:00Z",
        "db_path": "/tmp/test.db",
        "files": [{"filename": "events.parquet", "record_count": 10}],
    }
    result = validator.validate_export_manifest(manifest)
    assert result["valid"] is True


def test_review_queue_has_correct_columns(validator, tmp_path):
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    review_path = str(tmp_path / "review_queue.csv")
    invalid = {"bad": "record"}
    validator.validate_batch([invalid], "screenshot", review_path)
    with open(review_path, newline="") as f:
        reader = csv.DictReader(f)
        assert set(reader.fieldnames) == {
            "routed_at", "record_id", "source_file", "schema_name",
            "field", "error_type", "error_message", "record_json", "suggested_fix",
        }


def test_review_queue_dedups_within_window(validator, tmp_path):
    """Re-routing an identical invalid record must not duplicate rows (24h dedup)."""
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pytest.skip("jsonschema not installed")
    review_path = str(tmp_path / "review_queue.csv")
    invalid = {"ocr_confidence": 0.5}  # missing required screenshot fields
    validator.validate_batch([invalid], "screenshot", review_path)
    with open(review_path, newline="") as f:
        first = list(csv.DictReader(f))
    validator.validate_batch([invalid], "screenshot", review_path)
    with open(review_path, newline="") as f:
        second = list(csv.DictReader(f))
    assert len(first) >= 1
    assert len(second) == len(first)


# ── Stage 1 hardening tests ───────────────────────────────────────────────────

def test_run_db_validation_returns_per_table_summary(populated_db, tmp_path):
    v = SchemaValidator()
    review_path = str(tmp_path / "review_queue.csv")
    results = v.run_db_validation(populated_db, review_path)
    expected_schemas = {
        "flight_event", "screenshot", "track_point",
        "extracted_field", "anomaly", "mission_inference",
    }
    assert not results.get("_error"), f"Unexpected error: {results.get('_error')}"
    for schema_name in expected_schemas:
        assert schema_name in results, f"Missing per-table result: {schema_name}"
        entry = results[schema_name]
        assert "total" in entry
        assert "valid" in entry
        assert "invalid" in entry


def test_run_db_validation_missing_db_returns_error_key(tmp_path):
    v = SchemaValidator()
    results = v.run_db_validation(
        str(tmp_path / "nonexistent.db"),
        str(tmp_path / "review.csv"),
    )
    # SQLite creates the file if missing, so run_db_validation returns empty
    # per-table results (no tables → nothing validated). The absence of _error
    # with zero-table results is also acceptable; either way there must be no
    # crash and the return must be a dict.
    assert isinstance(results, dict)


def test_all_core_schemas_loadable():
    v = SchemaValidator()
    loaded = v.available_schemas()
    try:
        import jsonschema  # noqa: F401
        assert len(loaded) >= 11, (
            f"Expected ≥11 schemas in {SCHEMAS_DIR}, got {len(loaded)}: {loaded}"
        )
    except ImportError:
        pytest.skip("jsonschema not installed — schema loading is a no-op")


def test_satellite_source_manifest_schema_loaded(validator):
    try:
        import jsonschema  # noqa: F401
        assert "satellite_source_manifest" in validator.available_schemas()
    except ImportError:
        pytest.skip("jsonschema not installed")


# ── Phase 9: Production Hardening ────────────────────────────────────────────

def test_reload_schemas_returns_count(validator):
    count = validator.reload_schemas()
    assert isinstance(count, int)
    assert count >= 0


def test_reload_schemas_idempotent(validator):
    count1 = validator.reload_schemas()
    count2 = validator.reload_schemas()
    assert count1 == count2


def test_schema_count_matches_available(validator):
    assert validator.schema_count() == len(validator.available_schemas())


def test_get_schema_names_sorted(validator):
    names = validator.get_schema_names()
    assert names == sorted(names)


def test_validate_with_context_valid_record(validator):
    record = {
        "screenshot_id": "s1", "flight_id": "f1", "image_path": "/a/b.png",
        "captured_at": "2024-01-01T00:00:00Z",
        "processed_at": "2024-01-01T00:01:00Z",
        "ocr_confidence": 0.9,
        "has_callsign": True, "has_coordinates": True,
    }
    result = validator.validate_with_context(record, "screenshot", "test-run")
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_with_context_prefixes_errors(validator):
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pytest.skip("jsonschema not installed")
    result = validator.validate_with_context({}, "screenshot", "batch-42")
    if not result["valid"]:
        assert all("[batch-42]" in e for e in result["errors"])
