"""Regression tests for the machine-readable schema validation entry point."""

import json

from scripts import validate_schemas


def test_schema_index_rejects_unloaded_and_missing_schemas(tmp_path):
    index_path = tmp_path / "schema_index.json"
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "known.schema.json").write_text("{}", encoding="utf-8")
    index_path.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "artifact_path": "known.json",
                        "schema_name": "known",
                        "schema_file": "schemas/known.schema.json",
                    },
                    {
                        "artifact_path": "missing.json",
                        "schema_name": "missing",
                        "schema_file": "schemas/missing.schema.json",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    errors = validate_schemas.validate_schema_index(
        index_path, schemas_dir, {"known"}
    )

    assert any("missing schema_file" in error for error in errors)
    assert not any("known" in error for error in errors)


def test_schema_index_rejects_path_escape_and_duplicate_artifacts(tmp_path):
    index_path = tmp_path / "schema_index.json"
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    index_path.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "artifact_path": "same.json",
                        "schema_name": "outside",
                        "schema_file": "../outside.schema.json",
                    },
                    {
                        "artifact_path": "same.json",
                        "schema_name": "unregistered",
                        "schema_file": "schemas/unregistered.schema.json",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    errors = validate_schemas.validate_schema_index(index_path, schemas_dir, set())

    assert any("escapes the schema directory" in error for error in errors)
    assert any("duplicates artifact_path" in error for error in errors)


def test_validate_passes_at_minimum_schema_count(monkeypatch):
    schemas = [
        f"schema_{index}" for index in range(validate_schemas.MINIMUM_SCHEMA_COUNT)
    ]
    monkeypatch.setattr(
        validate_schemas.SchemaValidator,
        "available_schemas",
        lambda self: schemas,
    )
    monkeypatch.setattr(validate_schemas, "validate_schema_index", lambda *args: [])

    result = validate_schemas.validate()

    assert result == {
        "status": "PASS",
        "schema_count": validate_schemas.MINIMUM_SCHEMA_COUNT,
        "minimum_schema_count": validate_schemas.MINIMUM_SCHEMA_COUNT,
        "schemas": schemas,
        "index_errors": [],
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
    monkeypatch.setattr(validate_schemas, "validate_schema_index", lambda *args: [])

    assert validate_schemas.main(["--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL"
    assert result["schema_count"] == validate_schemas.MINIMUM_SCHEMA_COUNT - 1
    assert result["minimum_schema_count"] == validate_schemas.MINIMUM_SCHEMA_COUNT
    assert result["schemas"] == schemas
    assert result["index_errors"] == []


def test_main_json_fails_when_schema_index_has_stale_entry(monkeypatch, capsys):
    schemas = [
        f"schema_{index}" for index in range(validate_schemas.MINIMUM_SCHEMA_COUNT)
    ]
    monkeypatch.setattr(
        validate_schemas.SchemaValidator,
        "available_schemas",
        lambda self: schemas,
    )
    monkeypatch.setattr(
        validate_schemas,
        "validate_schema_index",
        lambda *args: ["artifacts[0] references missing schema"],
    )

    assert validate_schemas.main(["--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL"
    assert result["index_errors"] == ["artifacts[0] references missing schema"]


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
        "index_errors": [],
        "status": "FAIL",
    }
