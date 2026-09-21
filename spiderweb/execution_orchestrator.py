"""Unified LOCATION_QUERY execution orchestration.

This module composes, but does not replace, the canonical generic request
executor and specialized provider executor. Each lane writes its own immutable
receipt. The run receipt binds those subreceipts to the exact top-level plan.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.location_query_fetch import execute as execute_generic
from spiderweb.specialized_execution import execute_specialized_calls


class LocationRunError(RuntimeError):
    """Fail-closed unified execution error."""


def canonical_json_sha256(value: object) -> str:
    data = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _generic_subplan(plan: dict[str, Any]) -> dict[str, Any]:
    subplan = copy.deepcopy(plan)
    subplan["specialized_calls"] = []
    subplan["specialized_call_count"] = 0
    subplan["specialized_executor_provider_ids"] = []
    return subplan


def execute_location_query(
    plan: dict[str, Any],
    output_dir: Path,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    query = plan.get("query") or {}
    if query.get("mode") != "fetch":
        raise LocationRunError("unified execution requires query.mode=fetch")
    fetch_gate = str(plan.get("fetch_gate", "MISSING"))
    if fetch_gate not in {"READY", "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"}:
        raise LocationRunError(
            f"top-level fetch gate blocks execution: {fetch_gate}"
        )

    requests = plan.get("requests")
    specialized_calls = plan.get("specialized_calls", [])
    if not isinstance(requests, list):
        raise LocationRunError("plan.requests must be a list")
    if not isinstance(specialized_calls, list):
        raise LocationRunError("plan.specialized_calls must be a list")
    if plan.get("request_count") not in {None, len(requests)}:
        raise LocationRunError("plan request_count arithmetic drift")
    if plan.get("specialized_call_count") not in {None, len(specialized_calls)}:
        raise LocationRunError("plan specialized_call_count arithmetic drift")

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "run_receipt.json"
    if final_path.exists():
        raise LocationRunError(
            f"unified run receipt already exists: {final_path}"
        )

    full_plan_sha = canonical_json_sha256(plan)

    generic_dir = output_dir / "generic"
    generic_plan = _generic_subplan(plan)
    generic_receipt_path = generic_dir / "fetch_receipt.json"
    if requests:
        generic_receipt = execute_generic(
            generic_plan,
            generic_dir,
            timeout=timeout,
        )
        if not generic_receipt_path.is_file():
            raise LocationRunError("generic executor did not write fetch_receipt.json")
    else:
        generic_dir.mkdir(parents=True, exist_ok=True)
        generic_receipt = {
            "schema_version": "spiderweb.location_query_fetch_receipt.empty_lane.v1.0",
            "state": "PASS",
            "query_mode": "fetch",
            "plan_sha256": canonical_json_sha256(generic_plan),
            "execution_scope": "NO_GENERIC_REQUESTS",
            "fetch_gate": fetch_gate,
            "request_count": 0,
            "pass_count": 0,
            "no_coverage_count": 0,
            "failure_count": 0,
            "requests": [],
            "raw_bytes_preserved_before_derivation": True,
        }
        write_json(generic_receipt_path, generic_receipt)

    specialized_dir = output_dir / "specialized"
    specialized_receipt = execute_specialized_calls(
        plan,
        specialized_dir,
    )
    specialized_receipt_path = specialized_dir / "specialized_receipt.json"
    if not specialized_receipt_path.is_file():
        raise LocationRunError(
            "specialized executor did not write specialized_receipt.json"
        )

    generic_ok = generic_receipt.get("state") in {"PASS", "PARTIAL"}
    specialized_ok = specialized_receipt.get("state") == "PASS"
    if not generic_ok or not specialized_ok:
        state = "PARTIAL_OR_BLOCKED"
    elif fetch_gate == "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS":
        state = "PARTIAL"
    else:
        state = "PASS"

    result = {
        "schema_version": "spiderweb.location_query_run_receipt.v1.0",
        "state": state,
        "query_id": query.get("query_id"),
        "fetch_gate": fetch_gate,
        "full_plan_sha256": full_plan_sha,
        "provider_registry_sha256": plan.get("provider_registry_sha256"),
        "generic": {
            "subplan_sha256": canonical_json_sha256(generic_plan),
            "receipt_path": str(generic_receipt_path),
            "receipt_sha256": sha256_file(generic_receipt_path),
            "state": generic_receipt.get("state"),
            "request_count": generic_receipt.get("request_count"),
        },
        "specialized": {
            "receipt_path": str(specialized_receipt_path),
            "receipt_sha256": sha256_file(specialized_receipt_path),
            "state": specialized_receipt.get("state"),
            "call_count": specialized_receipt.get("call_count"),
        },
        "arithmetic": {
            "planned_generic_requests": len(requests),
            "executed_generic_requests": generic_receipt.get("request_count"),
            "planned_specialized_calls": len(specialized_calls),
            "executed_specialized_calls": specialized_receipt.get("call_count"),
            "generic_request_count_closed": generic_receipt.get("request_count") == len(requests),
            "specialized_call_count_closed": specialized_receipt.get("call_count") == len(specialized_calls),
        },
        "policy": {
            "specialized_and_generic_receipts_remain_separate": True,
            "source_manifestation_rows_not_aggregated": True,
            "raw_bytes_preserved_by_execution_lane": True,
            "plan_before_download": True,
        },
    }

    if not result["arithmetic"]["generic_request_count_closed"]:
        raise LocationRunError("generic request-count arithmetic did not close")
    if not result["arithmetic"]["specialized_call_count_closed"]:
        raise LocationRunError("specialized call-count arithmetic did not close")

    write_json(final_path, result)
    return result
