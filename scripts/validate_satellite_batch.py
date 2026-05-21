"""
EarthGPT iOS — Satellite batch validator.

Validates a batch of satellite imagery records in JSONL format and emits
a statistics summary JSON.

Usage:
    python -m scripts.validate_satellite_batch --in outputs/satellite_batch.jsonl
    python -m scripts.validate_satellite_batch --in outputs/satellite_batch.jsonl --out outputs/satellite_batch_stats.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from earthgpt.io_utils import iter_jsonl
from earthgpt.log_utils import log, warn


REQUIRED_FIELDS = ["lat", "lon", "timestamp"]
LAT_RANGE = (-90, 90)
LON_RANGE = (-180, 180)


def validate_record(record: dict) -> dict:
    """Validate a single satellite imagery record.

    Returns a dict with ``valid`` (bool) and ``errors`` (list of str).
    """
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing required field: {field}")

    lat = record.get("lat")
    lon = record.get("lon")
    if lat is not None:
        try:
            lat_f = float(lat)
            if not (LAT_RANGE[0] <= lat_f <= LAT_RANGE[1]):
                errors.append(f"lat out of range: {lat_f}")
        except (TypeError, ValueError):
            errors.append(f"lat not numeric: {lat!r}")

    if lon is not None:
        try:
            lon_f = float(lon)
            if not (LON_RANGE[0] <= lon_f <= LON_RANGE[1]):
                errors.append(f"lon out of range: {lon_f}")
        except (TypeError, ValueError):
            errors.append(f"lon not numeric: {lon!r}")

    return {"valid": len(errors) == 0, "errors": errors}


def run_batch_validation(input_path: str) -> dict:
    """Validate all records in *input_path* and return statistics."""
    total = 0
    valid_count = 0
    invalid_count = 0
    error_summary: dict = {}

    for record in iter_jsonl(input_path):
        total += 1
        result = validate_record(record)
        if result["valid"]:
            valid_count += 1
        else:
            invalid_count += 1
            for err in result["errors"]:
                error_summary[err] = error_summary.get(err, 0) + 1

    pass_rate = round(valid_count / total, 4) if total else 0.0

    stats = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": input_path,
        "total_records": total,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "pass_rate": pass_rate,
        "error_summary": error_summary,
        "overall_status": "PASS" if invalid_count == 0 else "FAIL",
    }
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a satellite imagery JSONL batch")
    parser.add_argument("--in", dest="input", required=True,
                        help="Input JSONL file of satellite records")
    parser.add_argument("--out", dest="output", default=None,
                        help="Optional output path for statistics JSON (default: stdout)")
    args = parser.parse_args()

    stats = run_batch_validation(args.input)

    stats_json = json.dumps(stats, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(stats_json)
        log(f"Validation statistics written to {args.output}")
    else:
        print(stats_json)

    log(f"Total: {stats['total_records']}  Valid: {stats['valid_records']}  "
        f"Invalid: {stats['invalid_records']}  Pass rate: {stats['pass_rate']:.1%}")

    if stats["overall_status"] != "PASS":
        warn(f"Batch validation FAILED — {stats['invalid_records']} invalid records")
        sys.exit(1)
    else:
        log("Batch validation PASSED.")


if __name__ == "__main__":
    main()
