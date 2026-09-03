"""Regression tests for the machine-readable schema validation entry point."""

import json

from scripts import validate_schemas


def test_validate_passes_at_minimum_schema_count(monkeypatch):
    schemas = [
        f"schema_{index}" for index in range(validate_schemas.MINIMUM_SCHEMA_COUNT)
    ]
    monkeypatch.setattr(
        validate_schemas.SchemaValidator,
        "available_schemas",
        lambda self: schemas,
    )

    result = validate_schemas.validate()

    assert result == {
        "status": "PASS",
        "schema_count": validate_schemas.MINIMUM_SCHEMA_COUNT,
        "minimum_schema_count": validate_schemas.MINIMUM_SCHEMA_COUNT,
        "schemas": schemas,
    }


def test_main_json_fails_below_minimum_schema_count(monkeypatch, capsys):
    schemas = [
        f"schema_{index}" for index in range(validate_schemas.MINIMUM_SCHEMA_COUNT - 1)
    ]
    monkeypatch.setattr(
        validate_schemas.SchemaValidator,
        "available_schemas",
        lambda self: schemas,
    )

    assert validate_schemas.main(["--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL"
    assert result["schema_count"] == validate_schemas.MINIMUM_SCHEMA_COUNT - 1
    assert result["minimum_schema_count"] == validate_schemas.MINIMUM_SCHEMA_COUNT
    assert result["schemas"] == schemas


def test_main_json_fails_closed_on_validator_error(monkeypatch, capsys):
    def raise_registry_error(self):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(
        validate_schemas.SchemaValidator,
        "available_schemas",
        raise_registry_error,
    )

    assert validate_schemas.main(["--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "error": "RuntimeError: registry unavailable",
        "minimum_schema_count": validate_schemas.MINIMUM_SCHEMA_COUNT,
        "schema_count": None,
        "schemas": [],
        "status": "FAIL",
    }
