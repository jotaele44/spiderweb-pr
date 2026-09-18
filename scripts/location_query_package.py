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


def canonical_json_sha256(value: object) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("fetch_receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(
            f"FAIL: package manifest already exists: {args.output}; use a new versioned output path"
        )

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    fetch = json.loads(args.fetch_receipt.read_text(encoding="utf-8"))

    query = plan.get("query") or {}
    execution_scope = str(fetch.get("execution_scope", ""))
    if query.get("mode") != "fetch" and execution_scope != "DISCOVERY_OR_RESOLVER_STAGE":
        raise SystemExit(
            "FAIL: package requires fetch-mode plan unless receipt is explicit discovery/resolver-stage execution"
        )
    canonical_plan_sha = canonical_json_sha256(plan)
    receipt_plan_sha = fetch.get("plan_sha256")
    if (
        not isinstance(receipt_plan_sha, str)
        or len(receipt_plan_sha) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in receipt_plan_sha)
    ):
        raise SystemExit("FAIL: fetch receipt lacks a valid executor plan SHA256")
    if receipt_plan_sha != canonical_plan_sha:
        raise SystemExit(
            f"FAIL: fetch receipt plan SHA drift expected={receipt_plan_sha} actual={canonical_plan_sha}"
        )
    requests = fetch.get("requests")
    if not isinstance(requests, list):
        raise SystemExit("FAIL: fetch receipt lacks requests list")
    if fetch.get("request_count") != len(requests):
        raise SystemExit("FAIL: fetch receipt request-count arithmetic drift")

    planned_requests = plan.get("requests")
    if not isinstance(planned_requests, list):
        raise SystemExit("FAIL: acquisition plan lacks requests list")

    if execution_scope == "DISCOVERY_OR_RESOLVER_STAGE":
        expected_plan_requests = [
            spec
            for spec in planned_requests
            if isinstance(spec, dict)
            and (
                "DISCOVERY" in str(spec.get("identity_state", "")).upper()
                or "RESOLVER_STAGE" in str(spec.get("identity_state", "")).upper()
            )
        ]
    else:
        expected_plan_requests = planned_requests

    expected_request_hashes = [
        canonical_json_sha256(spec)
        for spec in expected_plan_requests
    ]
    actual_request_hashes = [
        request.get("request_spec_sha256")
        for request in requests
    ]
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in value)
        for value in actual_request_hashes
    ):
        raise SystemExit("FAIL: fetch receipt contains malformed/missing request_spec_sha256")
    if actual_request_hashes != expected_request_hashes:
        raise SystemExit(
            "FAIL: plan/fetch request-spec vector mismatch "
            f"expected_count={len(expected_request_hashes)} actual_count={len(actual_request_hashes)}"
        )

    raw_records = []
    missing_raw = []
    hash_mismatch = []
    seen_raw_paths: set[str] = set()
    parent_denominator_hashes: set[str] = set()
    for request in requests:
        parent_hash = request.get("parent_denominator_sha256")
        if parent_hash is not None:
            if (
                not isinstance(parent_hash, str)
                or len(parent_hash) != 64
                or any(ch not in "0123456789abcdefABCDEF" for ch in parent_hash)
            ):
                raise SystemExit(
                    f"FAIL: malformed parent_denominator_sha256 for {request.get('provider_id')}/{request.get('request_role')}"
                )
            parent_denominator_hashes.add(parent_hash.lower())
        paths = []
        if request.get("raw_path"):
            paths.append((request["raw_path"], request.get("sha256")))
        if request.get("id_denominator_raw_path"):
            paths.append((request["id_denominator_raw_path"], request.get("id_denominator_sha256")))
        for batch in request.get("batches") or []:
            if batch.get("raw_path"):
                paths.append((batch["raw_path"], batch.get("sha256")))

        for raw_path, expected in paths:
            normalized_path = str(Path(raw_path))
            if normalized_path in seen_raw_paths:
                raise SystemExit(
                    f"FAIL: duplicate raw artifact path in fetch receipt: {normalized_path}"
                )
            seen_raw_paths.add(normalized_path)
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
    policy = plan.get("policy") or {}
    if policy.get("plan_before_download") is not True:
        raise SystemExit("FAIL: acquisition plan lacks plan_before_download=true")
    if policy.get("raw_bytes_before_derivation") is not True:
        raise SystemExit("FAIL: acquisition plan lacks raw_bytes_before_derivation=true")

    fetch_gate = str(fetch.get("fetch_gate", "MISSING"))
    if fetch.get("failure_count"):
        package_state = "PARTIAL_OR_BLOCKED"
    elif fetch_gate == "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS" or fetch.get("state") == "PARTIAL":
        package_state = "PARTIAL"
    elif fetch_gate == "READY" and fetch.get("state") == "PASS":
        package_state = "PASS"
    elif fetch_gate == "DISCOVERY_ONLY" and fetch.get("state") == "DISCOVERY_PASS":
        package_state = "DISCOVERY_PASS"
    else:
        package_state = "BLOCKED_UNRESOLVED_EXECUTION_STATE"

    result = {
        "schema_version": "spiderweb.location_query_package.v1.3",
        "state": package_state,
        "fetch_gate": fetch_gate,
        "fetch_blocker_provider_ids": fetch.get("fetch_blocker_provider_ids", []),
        "query_id": query.get("query_id"),
        "plan": {
            "path": str(args.plan),
            "byte_sha256": sha256_file(args.plan),
            "canonical_json_sha256": canonical_plan_sha,
            "executor_plan_sha256": receipt_plan_sha,
            "canonical_hash_matches_executor": receipt_plan_sha == canonical_plan_sha,
        },
        "fetch_receipt": {
            "path": str(args.fetch_receipt),
            "sha256": sha256_file(args.fetch_receipt),
        },
        "provider_denominator_count": plan.get("provider_denominator_count"),
        "request_count": fetch.get("request_count"),
        "planned_request_count_for_execution_scope": len(expected_plan_requests),
        "pass_count": fetch.get("pass_count"),
        "no_coverage_count": fetch.get("no_coverage_count", 0),
        "failure_count": fetch.get("failure_count"),
        "raw_artifact_count": len(raw_records),
        "total_raw_bytes": total_raw_bytes,
        "parent_denominator_hash_count": len(parent_denominator_hashes),
        "parent_denominator_sha256": sorted(parent_denominator_hashes),
        "raw_artifacts": raw_records,
        "invariants": {
            "raw_artifacts_exist": not missing_raw,
            "raw_hashes_match_receipts": not hash_mismatch,
            "executor_plan_hash_matches": receipt_plan_sha == canonical_plan_sha,
            "request_spec_vector_equal": actual_request_hashes == expected_request_hashes,
            "parent_denominator_hashes_well_formed": True,
            "plan_before_download": True,
            "raw_bytes_before_derivation": True,
            "raw_artifact_paths_unique": len(seen_raw_paths) == len(raw_records),
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
    return 0 if result["state"] in {"PASS", "PARTIAL", "DISCOVERY_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
