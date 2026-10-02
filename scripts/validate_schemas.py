#!/usr/bin/env python3
"""Validate the Spiderweb schema registry without invoking a shell or Make.

This is the executable entry point used by TheHub's GUI operations plane.  It
wraps the same ``SchemaValidator.available_schemas()`` check historically
embedded in ``make validate-schemas`` while providing a stable ``--json`` mode
for machine consumption.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integration.schema_validation import SCHEMAS_DIR, SchemaValidator  # noqa: E402

MINIMUM_SCHEMA_COUNT = 11
SCHEMA_INDEX_PATH = REPO_ROOT / "schemas" / "schema_index.json"


def validate_schema_index(
    index_path: Path, schemas_dir: Path, loaded_schemas: set[str]
) -> list[str]:
    """Check that every schema-bearing registry entry resolves to a loaded schema."""
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read schema index: {type(exc).__name__}: {exc}"]

    artifacts = index.get("artifacts") if isinstance(index, dict) else None
    if not isinstance(artifacts, list):
        return ["schema index must contain an artifacts list"]

    errors: list[str] = []
    seen_artifacts: set[str] = set()
    schema_root = schemas_dir.resolve()
    for position, entry in enumerate(artifacts):
        label = f"artifacts[{position}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue

        artifact_path = entry.get("artifact_path")
        if not isinstance(artifact_path, str) or not artifact_path.strip():
            errors.append(f"{label} has no artifact_path")
        elif artifact_path in seen_artifacts:
            errors.append(f"{label} duplicates artifact_path {artifact_path!r}")
        else:
            seen_artifacts.add(artifact_path)

        schema_name = entry.get("schema_name")
        schema_file = entry.get("schema_file")
        if schema_name is None and schema_file is None:
            if entry.get("format") != "markdown" or not entry.get("notes"):
                errors.append(f"{label} is missing a schema without a documented exception")
            continue
        if not isinstance(schema_name, str) or not schema_name:
            errors.append(f"{label} must define schema_name when schema_file is set")
            continue
        if not isinstance(schema_file, str) or not schema_file:
            errors.append(f"{label} must define schema_file for {schema_name!r}")
            continue

        resolved_file = (schemas_dir.parent / schema_file).resolve()
        if not resolved_file.is_relative_to(schema_root):
            errors.append(f"{label} schema_file escapes the schema directory")
            continue
        if not resolved_file.is_file():
            errors.append(f"{label} references missing schema_file {schema_file!r}")
            continue
        if resolved_file.name != f"{schema_name}.schema.json":
            errors.append(f"{label} schema_file does not match schema_name {schema_name!r}")
        if schema_name not in loaded_schemas:
            errors.append(f"{label} schema {schema_name!r} is not loaded")
    return errors


def validate() -> dict[str, object]:
    validator = SchemaValidator()
    schemas = list(validator.available_schemas())
    count = len(schemas)
    index_errors = validate_schema_index(
        SCHEMA_INDEX_PATH, SCHEMAS_DIR, set(schemas)
    )
    passed = count >= MINIMUM_SCHEMA_COUNT and not index_errors
    return {
        "status": "PASS" if passed else "FAIL",
        "schema_count": count,
        "minimum_schema_count": MINIMUM_SCHEMA_COUNT,
        "schemas": schemas,
        "index_errors": index_errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit a machine-readable result"
    )
    args = parser.parse_args(argv)

    try:
        result = validate()
    except Exception as exc:  # fail closed while preserving a machine-readable error
        result = {
            "status": "FAIL",
            "schema_count": None,
            "minimum_schema_count": MINIMUM_SCHEMA_COUNT,
            "schemas": [],
            "index_errors": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            print(f"FAIL: {result['error']}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            f"Loaded {result['schema_count']} schemas: {result['schemas']} "
            f"(minimum {MINIMUM_SCHEMA_COUNT})"
        )

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
