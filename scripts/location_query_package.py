#!/usr/bin/env python3
"""Freeze a LOCATION_QUERY plan + fetch receipt into an auditable package manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("fetch_receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    fetch = json.loads(args.fetch_receipt.read_text(encoding="utf-8"))

    query = plan.get("query") or {}
    if query.get("mode") != "fetch":
        raise SystemExit("FAIL: package requires a fetch-mode acquisition plan")
    requests = fetch.get("requests")
    if not isinstance(requests, list):
        raise SystemExit("FAIL: fetch receipt lacks requests list")
    if fetch.get("request_count") != len(requests):
        raise SystemExit("FAIL: fetch receipt request-count arithmetic drift")

    raw_records = []
    missing_raw = []
    hash_mismatch = []
    for request in requests:
        paths = []
        if request.get("raw_path"):
            paths.append((request["raw_path"], request.get("sha256")))
        if request.get("id_denominator_raw_path"):
            paths.append((request["id_denominator_raw_path"], request.get("id_denominator_sha256")))
        for batch in request.get("batches") or []:
            if batch.get("raw_path"):
                paths.append((batch["raw_path"], batch.get("sha256")))

        for raw_path, expected in paths:
            path = Path(raw_path)
            if not path.is_file():
                missing_raw.append(str(path))
                continue
            actual = sha256_file(path)
            if expected and actual != expected:
                hash_mismatch.append({
                    "path": str(path),
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                })
            raw_records.append({
                "path": str(path),
                "sha256": actual,
                "bytes": path.stat().st_size,
            })

    if missing_raw or hash_mismatch:
        raise SystemExit(
            f"FAIL: raw artifact verification failed missing={missing_raw[:20]} mismatches={hash_mismatch[:20]}"
        )

    total_raw_bytes = sum(row["bytes"] for row in raw_records)
    result = {
        "schema_version": "spiderweb.location_query_package.v1.0",
        "state": "PASS" if fetch.get("failure_count") == 0 else "PARTIAL_OR_BLOCKED",
        "query_id": query.get("query_id"),
        "plan": {
            "path": str(args.plan),
            "sha256": sha256_file(args.plan),
        },
        "fetch_receipt": {
            "path": str(args.fetch_receipt),
            "sha256": sha256_file(args.fetch_receipt),
        },
        "provider_denominator_count": plan.get("provider_denominator_count"),
        "request_count": fetch.get("request_count"),
        "pass_count": fetch.get("pass_count"),
        "no_coverage_count": fetch.get("no_coverage_count", 0),
        "failure_count": fetch.get("failure_count"),
        "raw_artifact_count": len(raw_records),
        "total_raw_bytes": total_raw_bytes,
        "raw_artifacts": raw_records,
        "invariants": {
            "raw_artifacts_exist": not missing_raw,
            "raw_hashes_match_receipts": not hash_mismatch,
            "plan_before_download": bool((plan.get("policy") or {}).get("plan_before_download")),
            "raw_bytes_before_derivation": bool((plan.get("policy") or {}).get("raw_bytes_before_derivation")),
            "source_manifestations_not_aggregated": True,
        },
    }
    write_json(args.output, result)
    print(json.dumps({
        "state": result["state"],
        "query_id": result["query_id"],
        "raw_artifact_count": result["raw_artifact_count"],
        "total_raw_bytes": total_raw_bytes,
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if result["state"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
