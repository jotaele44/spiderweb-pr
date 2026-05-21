"""
EarthGPT iOS — JSONL validator.

Counts valid and invalid rows in a JSONL file.
Critical for iOS resumable execution.

Usage:
    python -m scripts.validate_jsonl outputs/geo_queue.jsonl
    python -m scripts.validate_jsonl outputs/geo_queue.jsonl --schema flight_event
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import count_jsonl, iter_jsonl
from earthgpt.log_utils import log


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a JSONL file")
    parser.add_argument("path", help="Path to the JSONL file to validate")
    parser.add_argument(
        "--schema",
        dest="schema",
        default=None,
        help="Named schema to validate each record against (uses SchemaValidator)",
    )
    args = parser.parse_args()

    path = args.path
    valid, invalid = count_jsonl(path)
    total = valid + invalid

    log(f"File   : {path}")
    log(f"Valid  : {valid}")
    log(f"Invalid: {invalid}")
    log(f"Total  : {total}")

    if invalid > 0:
        log(f"WARNING: {invalid} malformed lines detected", prefix="WARN")
    else:
        log("All lines valid.")

    if args.schema:
        try:
            from schema_validation import SchemaValidator
            validator = SchemaValidator()
            schema_invalid = 0
            schema_valid = 0
            for record in iter_jsonl(path):
                result = validator.validate(record, args.schema)
                if result["valid"]:
                    schema_valid += 1
                else:
                    schema_invalid += 1
            log(f"Schema : {args.schema}")
            log(f"Schema-valid  : {schema_valid}")
            log(f"Schema-invalid: {schema_invalid}")
            if schema_invalid > 0:
                log(f"WARNING: {schema_invalid} records failed schema '{args.schema}'", prefix="WARN")
            else:
                log(f"All records pass schema '{args.schema}'.")
        except Exception as e:
            log(f"Schema validation error: {e}", prefix="WARN")


if __name__ == "__main__":
    main()
