"""Offline reference-AOI planning corpus for Spiderweb LOCATION_QUERY."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from spiderweb.location_query import load_registry, route_query


class ReferenceCorpusError(ValueError):
    """Fail-closed reference corpus error."""


def canonical_sha256(value: object) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def build_reference_corpus(
    reference_payload: dict[str, Any],
    *,
    registry: dict[str, Any],
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if reference_payload.get("schema_version") != "spiderweb.location_query_reference_aois.v1.0":
        raise ReferenceCorpusError("reference AOI schema_version drift")
    rows = reference_payload.get("reference_aois")
    if not isinstance(rows, list) or not rows:
        raise ReferenceCorpusError("reference AOI denominator missing")
    ids = [str(row.get("id", "")).strip() for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or any(not value for value in ids):
        raise ReferenceCorpusError("reference AOI id missing")
    if len(ids) != len(set(ids)):
        raise ReferenceCorpusError("reference AOI ids are not unique")

    plans: list[dict[str, Any]] = []
    total_provider_decisions = 0
    total_requests = 0
    route_state_counts: dict[str, int] = {}

    for row in rows:
        query = {
            "query_id": row["id"],
            "geometry": row["geometry"],
            "mode": "plan",
            "allow_partial": False,
        }
        plan = route_query(query, registry=registry, env={} if env is None else env)
        if plan["query"]["mode"] != "plan" or plan["fetch_gate"] != "NOT_REQUESTED":
            raise ReferenceCorpusError(f"{row['id']}: planning gate drift")
        total_provider_decisions += int(plan["provider_denominator_count"])
        total_requests += int(plan["request_count"])
        for state, count in plan["route_state_counts"].items():
            route_state_counts[state] = route_state_counts.get(state, 0) + int(count)
        plans.append({
            "id": row["id"],
            "purpose": row.get("purpose"),
            "geometry": row["geometry"],
            "plan_sha256": canonical_sha256(plan),
            "provider_denominator_count": plan["provider_denominator_count"],
            "request_count": plan["request_count"],
            "route_state_counts": plan["route_state_counts"],
            "fetch_gate": plan["fetch_gate"],
            "plan": plan,
        })

    if len(plans) != len(rows):
        raise ReferenceCorpusError("reference AOI row conservation failed")

    return {
        "schema_version": "spiderweb.location_query_reference_corpus_receipt.v1.0",
        "state": "PASS",
        "reference_aoi_count": len(rows),
        "reference_aoi_ids": ids,
        "reference_payload_sha256": canonical_sha256(reference_payload),
        "provider_registry_sha256": canonical_sha256(registry),
        "total_provider_decisions": total_provider_decisions,
        "total_request_specs": total_requests,
        "aggregate_route_state_counts": dict(sorted(route_state_counts.items())),
        "network_requests": 0,
        "plans": plans,
        "invariants": {
            "row_conservation": len(plans) == len(rows),
            "unique_reference_ids": len(ids) == len(set(ids)),
            "all_plan_mode": all(item["plan"]["query"]["mode"] == "plan" for item in plans),
            "all_fetch_gate_not_requested": all(item["fetch_gate"] == "NOT_REQUESTED" for item in plans),
            "network_requests_zero": True,
        },
    }


def run_reference_corpus(
    *,
    reference_path: Path,
    registry_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    references = json.loads(reference_path.read_text(encoding="utf-8"))
    registry = load_registry(registry_path)
    result = build_reference_corpus(references, registry=registry, env={})
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in result["plans"]:
        path = output_dir / f"{item['id']}.acquisition_plan.json"
        path.write_text(json.dumps(item["plan"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = output_dir / "LOCATION_QUERY_REFERENCE_CORPUS.json"
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
