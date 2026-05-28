"""
Federation export contract — schema tests.

For each of the 5 schemas:
  - the schema itself is a valid Draft-7 schema
  - the canonical fixture validates with zero errors
  - dropping required `source_id` (or its equivalent) makes the row invalid
"""

import copy
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "valid_airspace_export"

STREAM_FILES = {
    "spiderweb_event":       "airspace_events.jsonl",
    "spiderweb_observation": "observations.jsonl",
    "spiderweb_track":       "tracks.jsonl",
    "spiderweb_source":      "sources.jsonl",
}

ALL_SCHEMAS = ["spiderweb_airspace_export"] + list(STREAM_FILES.keys())


def _load(schema_id: str) -> dict:
    with open(SCHEMAS_DIR / f"{schema_id}.schema.json") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("schema_id", ALL_SCHEMAS)
def test_schema_itself_is_valid(schema_id):
    schema = _load(schema_id)
    jsonschema.Draft7Validator.check_schema(schema)


@pytest.mark.parametrize("schema_id,filename", list(STREAM_FILES.items()))
def test_fixture_rows_validate(schema_id, filename):
    schema = _load(schema_id)
    validator = jsonschema.Draft7Validator(schema)
    rows = _read_jsonl(FIXTURE_DIR / filename)
    assert rows, f"fixture {filename} is empty"
    for i, row in enumerate(rows):
        errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
        assert not errors, f"{filename} row {i} invalid: " + "; ".join(e.message for e in errors)


def test_manifest_validates_against_export_schema():
    schema = _load("spiderweb_airspace_export")
    with open(FIXTURE_DIR / "manifest.json") as f:
        manifest = json.load(f)
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(manifest), key=lambda e: list(e.path))
    assert not errors, "manifest invalid: " + "; ".join(e.message for e in errors)


@pytest.mark.parametrize("schema_id,filename", list(STREAM_FILES.items()))
def test_dropping_source_id_invalidates_row(schema_id, filename):
    schema = _load(schema_id)
    validator = jsonschema.Draft7Validator(schema)
    rows = _read_jsonl(FIXTURE_DIR / filename)
    bad = copy.deepcopy(rows[0])
    bad.pop("source_id", None)
    errors = list(validator.iter_errors(bad))
    assert errors, f"expected {filename} row missing source_id to fail validation"
    assert any("source_id" in e.message for e in errors), "expected source_id-specific error"


@pytest.mark.parametrize("schema_id,filename,required_field", [
    ("spiderweb_event",       "airspace_events.jsonl", "event_time"),
    ("spiderweb_observation", "observations.jsonl",    "observed_at"),
    ("spiderweb_track",       "tracks.jsonl",          "observed_at"),
    ("spiderweb_source",      "sources.jsonl",         "first_seen_at"),
])
def test_dropping_timestamp_invalidates_row(schema_id, filename, required_field):
    schema = _load(schema_id)
    validator = jsonschema.Draft7Validator(schema)
    rows = _read_jsonl(FIXTURE_DIR / filename)
    bad = copy.deepcopy(rows[0])
    bad.pop(required_field, None)
    errors = list(validator.iter_errors(bad))
    assert errors, f"expected {filename} row missing {required_field} to fail validation"


@pytest.mark.parametrize("schema_id,filename", list(STREAM_FILES.items()))
def test_dropping_confidence_invalidates_row(schema_id, filename):
    schema = _load(schema_id)
    validator = jsonschema.Draft7Validator(schema)
    rows = _read_jsonl(FIXTURE_DIR / filename)
    bad = copy.deepcopy(rows[0])
    bad.pop("confidence", None)
    errors = list(validator.iter_errors(bad))
    assert errors
