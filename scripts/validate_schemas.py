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

from integration.schema_validation import SchemaValidator  # noqa: E402

MINIMUM_SCHEMA_COUNT = 11


def validate() -> dict[str, object]:
    validator = SchemaValidator()
    schemas = list(validator.available_schemas())
    count = len(schemas)
    passed = count >= MINIMUM_SCHEMA_COUNT
    return {
        "status": "PASS" if passed else "FAIL",
        "schema_count": count,
        "minimum_schema_count": MINIMUM_SCHEMA_COUNT,
        "schemas": schemas,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable result")
    args = parser.parse_args(argv)

    try:
        result = validate()
    except Exception as exc:  # fail closed while preserving a machine-readable error
        result = {
            "status": "FAIL",
            "schema_count": None,
            "minimum_schema_count": MINIMUM_SCHEMA_COUNT,
            "schemas": [],
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
