"""
EarthGPT iOS — JSONL validator with optional JSON Schema validation.

Counts valid and invalid rows in a JSONL file. When --schema is given,
each row is also validated against the named schema from schemas/.

Usage:
    python -m scripts.validate_jsonl <path.jsonl>
    python -m scripts.validate_jsonl <path.jsonl> --schema flight_event
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import count_jsonl
from earthgpt.log_utils import log


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a JSONL file.")
    parser.add_argument("path", help="Path to the .jsonl file")
    parser.add_argument(
        "--schema",
        metavar="SCHEMA_NAME",
        default=None,
        help="Optional schema name (e.g. flight_event) to validate each row against",
    )
    args = parser.parse_args()

    valid, invalid = count_jsonl(args.path)
    total = valid + invalid

    log(f"File   : {args.path}")
    log(f"Valid  : {valid}")
    log(f"Invalid: {invalid}")
    log(f"Total  : {total}")

    if invalid > 0:
        log(f"WARNING: {invalid} malformed lines detected", prefix="WARN")
    else:
        log("All lines valid.")

    if args.schema:
        _validate_schema(args.path, args.schema)


def _validate_schema(path: str, schema_name: str) -> None:
    try:
        from integration.schema_validation import SchemaValidator
    except ImportError as e:
        log(f"WARNING: schema validation skipped ({e})", prefix="WARN")
        return

    validator = SchemaValidator()
    if schema_name not in validator.available_schemas():
        log(
            f"ERROR: schema '{schema_name}' not found. "
            f"Available: {validator.available_schemas()}",
            prefix="ERR",
        )
        sys.exit(1)

    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    schema_valid = sum(1 for r in rows if validator.validate(r, schema_name)["valid"])
    schema_invalid = len(rows) - schema_valid

    log(f"Schema : {schema_name}")
    log(f"  Passed : {schema_valid}")
    log(f"  Failed : {schema_invalid}")

    if schema_invalid > 0:
        log(f"WARNING: {schema_invalid} rows failed schema validation", prefix="WARN")
        sys.exit(1)
    else:
        log("Schema validation passed.")


if __name__ == "__main__":
    main()
