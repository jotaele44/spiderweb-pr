"""Tests for SchemaValidator: valid/invalid routing."""

import csv
from pathlib import Path

import pytest

from schema_validation import SchemaValidator


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
        assert n_invalid == 1
        assert len(valid_records) == 1
        assert Path(review_path).exists()
        with open(review_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["schema_name"] == "screenshot"
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
        assert set(reader.fieldnames) == {"schema_name", "record_json", "errors", "routed_at"}
