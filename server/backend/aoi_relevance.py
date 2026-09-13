"""Dataset recommendations backed by exact file-footprint decisions.

Internal adapter over the unchanged v1.1 planner. No provider preference,
name-based equivalence, catalog acquisition, source download or coverage claim.
Every negative finding is bounded to the examined pinned snapshot.
"""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .aoi_planner import build_plan, digest

POSITIVE = frozenset({"FULLY_WITHIN", "PARTIAL"})
SPATIAL_STATES = POSITIVE | {"TOUCH_ONLY", "OUTSIDE", "NULL_EMPTY", "UNRESOLVED"}
DISPOSITIONS = frozenset({"RETAINED", "EXCLUDED", "UNRESOLVED"})
RECOMMENDATION_STATES = (
    "RECOMMENDED", "RELEVANT_UNRESOLVED", "FILTERED_OUT", "PROCESSING_ONLY",
    "NO_MATCH_IN_SNAPSHOT", "UNRESOLVED",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def summarize_plan(plan: dict, registry: dict) -> dict:
    """Build an immutable recommendation envelope from a server-produced plan.

    The public endpoint accepts AOI/filter inputs, NEVER a caller-supplied plan.
    Hash checks detect accidental changes; they are not source authentication.
    """
    _require(plan.get("schema_version") == "aoi_acquisition_plan.v1.1", "unsupported plan version")
    payload = {k: v for k, v in plan.items() if k not in {"plan_id", "plan_sha256"}}
    _require(digest(payload) == plan.get("plan_sha256"), "plan hash mismatch")
    _require(plan.get("plan_id") == f"aoi-{plan['plan_sha256']}", "plan ID mismatch")
    _require(plan.get("provider_registry_sha256") == digest(registry), "registry snapshot changed")
    _require(plan.get("capabilities") == {"fetch": False}, "unexpected acquisition capability")
    _require(plan.get("coverage") is None and plan.get("coverage_state") == "UNKNOWN",
             "unexpected valid-data coverage claim")
    _require(plan.get("certification") == "OPEN", "unexpected certification claim")
    entries = registry.get("providers", {}) if isinstance(registry, dict) else {}
    entries = entries if isinstance(entries, dict) else {}
    _require(all(isinstance(k, str) and k for k in entries), "invalid dataset registry key")

    catalogs = plan.get("catalogs")
    rows = plan.get("assets")
    _require(isinstance(catalogs, list) and isinstance(rows, list), "missing catalogs/assets")
    catalog_ids = [c.get("dataset_id") for c in catalogs if isinstance(c, dict)]
    _require(len(catalog_ids) == len(catalogs) and Counter(catalog_ids) == Counter(entries.keys()),
             "dataset denominator mismatch or duplicate catalog")
    catalog_by_id = {c["dataset_id"]: c for c in catalogs}
    grouped: dict[str, list[dict]] = defaultdict(list)
    observed_ids: set[str] = set()
    for row in rows:
        _require(isinstance(row, dict), "invalid asset row")
        row_id = row.get("row_id")
        _require(isinstance(row_id, str) and bool(row_id) and row_id not in observed_ids,
                 "duplicate/missing row ID")
        observed_ids.add(row_id)
        _require(row.get("dataset_id") in entries, "orphan file row")
        _require(row.get("relation") in SPATIAL_STATES and
                 row.get("processing_relation") in SPATIAL_STATES, "invalid spatial state")
        _require(row.get("disposition") in DISPOSITIONS, "invalid disposition")
        _require(type(row.get("required")) is bool, "invalid required flag")
        if row["disposition"] == "RETAINED":
            _require(row["required"] and row["processing_relation"] in POSITIVE and
                     row.get("source_status") == "SOURCE_BOUND" and bool(row.get("asset_key")),
                     "retained file is not bound to a positive-area match")
        if row["disposition"] == "EXCLUDED":
            _require(not row["required"], "excluded file marked required")
        if row["required"]:
            _require(row["processing_relation"] in POSITIVE, "required file lacks exact overlap")
        grouped[row["dataset_id"]].append(row)
    counts = plan.get("counts", {})
    expected = {
        "discovered": len(rows),
        "retained": sum(r["disposition"] == "RETAINED" for r in rows),
        "excluded": sum(r["disposition"] == "EXCLUDED" for r in rows),
        "unresolved": sum(r["disposition"] == "UNRESOLVED" for r in rows),
        "required": sum(r["required"] for r in rows), "cache_valid": 0,
        "fetch_required": sum(r["required"] and r["disposition"] == "RETAINED" for r in rows),
        "blocked_required": sum(r["required"] and r["disposition"] == "UNRESOLVED" for r in rows),
    }
    _require(all(_count(counts.get(k)) and counts[k] == v for k, v in expected.items()),
             "file denominator/counter mismatch")
    _require(plan.get("arithmetic_closed") is True, "plan arithmetic not closed")

    datasets = []
    for dataset_id in sorted(entries):
        provider = entries[dataset_id]
        provider = provider if isinstance(provider, dict) else {}
        catalog = catalog_by_id[dataset_id]
        members = grouped[dataset_id]
        _require(_count(catalog.get("records")) and catalog["records"] == len(members),
                 "catalog file denominator mismatch")
        _require(catalog.get("state") in {"PASS", "BLOCKED"}, "invalid catalog state")
        _require(catalog["state"] == "PASS" or not members, "blocked catalog emitted file rows")
        spatial = [r for r in members if r["relation"] in POSITIVE]
        applicable = [r for r in spatial if r["disposition"] == "RETAINED"]
        processing_only = [r for r in members if r["relation"] not in POSITIVE and
                           r["processing_relation"] in POSITIVE and r["disposition"] == "RETAINED"]
        unknown_geometry = [r for r in members if r["relation"] in {"NULL_EMPTY", "UNRESOLVED"}]
        unresolved_rows = [r for r in members if r["disposition"] == "UNRESOLVED"]
        bound = catalog["state"] == "PASS"
        complete = bound and not unresolved_rows
        if applicable:
            state = "RECOMMENDED"
        elif not bound or unknown_geometry:
            state = "UNRESOLVED"
        elif any(r["disposition"] == "UNRESOLVED" for r in spatial):
            state = "RELEVANT_UNRESOLVED"
        elif spatial:
            state = "FILTERED_OUT"
        elif processing_only:
            state = "PROCESSING_ONLY"
        else:
            state = "NO_MATCH_IN_SNAPSHOT"
        spatial_state = "RELEVANT" if spatial else (
            "UNRESOLVED" if not bound or unknown_geometry else "NO_POSITIVE_OVERLAP_IN_SNAPSHOT")
        reasons = []
        if not bound:
            reasons.append(catalog.get("reason") or "CATALOG_UNRESOLVED")
        if unresolved_rows:
            reasons.append("FILE_RESOLUTION_INCOMPLETE: inspect unresolved_row_ids")
        if not members and bound:
            reasons.append("EMPTY_PINNED_SNAPSHOT: not acquisition READY")
        datasets.append({
            "dataset_id": dataset_id,
            "label_raw": provider.get("label") if isinstance(provider.get("label"), str) else dataset_id,
            "provider_id": provider.get("provider_id") if isinstance(provider.get("provider_id"), str) else None,
            "catalog_sha256": catalog.get("sha256"),
            "scope": "configured_snapshot_only", "recommendation_state": state,
            "recommended": bool(applicable), "spatial_relevance": spatial_state,
            "file_resolution_state": "PASS" if complete else "UNRESOLVED",
            "counts": {"examined": len(members), "spatial_matches": len(spatial),
                       "applicable_files": len(applicable), "processing_only_files": len(processing_only),
                       "excluded": sum(r["disposition"] == "EXCLUDED" for r in members),
                       "unresolved": len(unresolved_rows)},
            "all_row_ids": [r["row_id"] for r in members],
            "spatial_match_row_ids": [r["row_id"] for r in spatial],
            "applicable_file_row_ids": [r["row_id"] for r in applicable],
            "processing_only_file_row_ids": [r["row_id"] for r in processing_only],
            "unresolved_row_ids": [r["row_id"] for r in unresolved_rows],
            "known_applicable_bytes": sum(r["size_bytes"] or 0 for r in applicable),
            "unknown_applicable_sizes": sum(r["size_bytes"] is None for r in applicable),
            "comparison_relation": "UNADJUDICATED", "reasons": reasons,
        })
    state_counts = {s: sum(d["recommendation_state"] == s for d in datasets)
                    for s in RECOMMENDATION_STATES}
    _require(sum(state_counts.values()) == len(entries), "dataset partition does not close")
    _require(sum(d["counts"]["examined"] for d in datasets) == len(rows), "file join multiplication/loss")
    result = {
        "schema_version": "aoi_dataset_relevance.v1.0",
        "scope": "configured_hash_pinned_catalog_snapshots_only",
        "registry_sha256": plan["provider_registry_sha256"], "aoi_sha256": plan["aoi_sha256"],
        "plan": copy.deepcopy(plan), "datasets": datasets,
        "recommended_dataset_ids": [d["dataset_id"] for d in datasets if d["recommended"]],
        "processing_only_dataset_ids": [d["dataset_id"] for d in datasets
                                        if d["recommendation_state"] == "PROCESSING_ONLY"],
        "unresolved_dataset_ids": [d["dataset_id"] for d in datasets
                                   if d["file_resolution_state"] == "UNRESOLVED"],
        "counts": {"datasets_examined": len(entries), "dataset_states": state_counts,
                   "file_rows_examined": len(rows)},
        "arithmetic_closed": True, "global_catalog_completeness": "UNRESOLVED",
        "source_equivalence": "NOT_INFERRED", "fetch_enabled": False,
        "coverage_state": "UNKNOWN", "certification": "OPEN",
        "hash_convention": "sorted-keys-ascii-json-excluding-response_id-and-response_sha256",
    }
    result["response_sha256"] = digest(result)
    result["response_id"] = f"aoi-relevance-{result['response_sha256']}"
    return result


def build_recommendations(request: dict, registry: dict, root: Path) -> dict:
    """Evaluate all configured datasets, then resolve their exact member files."""
    return summarize_plan(build_plan(request, registry, root), registry)
