"""SSURGO dependent-stage planner for Spiderweb LOCATION_QUERY.

Stage 1 is the AOI WFS acquisition emitted by location_query_sources. This module
consumes the preserved MapunitPoly raw manifestation, extracts the exact MUKEY
set, and emits bounded SDA tabular POST requests for mapunit and component.
It never infers historical equivalence and never flattens MUKEY->COKEY 1:N.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any

SDA_TABULAR_ENDPOINT = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"


class SSURGOChainError(ValueError):
    """Fail-closed SSURGO chain error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_mukeys_from_gml(raw: bytes) -> list[str]:
    if not raw:
        raise SSURGOChainError("MapunitPoly raw bytes are empty")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SSURGOChainError(f"MapunitPoly XML parse failure: {exc}") from exc
    values: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].casefold() != "mukey":
            continue
        value = (element.text or "").strip()
        if not value:
            raise SSURGOChainError("MapunitPoly contains null/empty MUKEY")
        if not value.isdigit():
            raise SSURGOChainError(f"MapunitPoly contains non-numeric MUKEY: {value!r}")
        values.append(value)
    if not values:
        raise SSURGOChainError("MapunitPoly contains no MUKEY values")
    return sorted(set(values), key=int)


def canonical_mukey_sha256(mukeys: list[str]) -> str:
    return sha256_bytes(("\n".join(mukeys) + "\n").encode("utf-8"))


def _quoted_in(mukeys: list[str]) -> str:
    if not mukeys or any(not value.isdigit() for value in mukeys):
        raise SSURGOChainError("certified MUKEY vector is empty or non-numeric")
    return ", ".join(f"'{value}'" for value in mukeys)


def build_stage2_plan(*, query: dict[str, Any], mapunitpoly_raw: bytes, mapunitpoly_receipt: dict[str, Any]) -> dict[str, Any]:
    if mapunitpoly_receipt.get("provider_id") != "SSURGO_SOILS":
        raise SSURGOChainError("receipt provider_id is not SSURGO_SOILS")
    if mapunitpoly_receipt.get("request_role") != "MapunitPoly":
        raise SSURGOChainError("receipt request_role is not MapunitPoly")
    if mapunitpoly_receipt.get("state") != "PASS":
        raise SSURGOChainError("MapunitPoly acquisition receipt is not PASS")
    actual_raw_sha = sha256_bytes(mapunitpoly_raw)
    if mapunitpoly_receipt.get("sha256") != actual_raw_sha:
        raise SSURGOChainError("MapunitPoly raw SHA256 does not match receipt")
    mukeys = extract_mukeys_from_gml(mapunitpoly_raw)
    in_clause = _quoted_in(mukeys)
    sqls = (
        ("mapunit", "SELECT * FROM mapunit " + f"WHERE mukey IN ({in_clause}) ORDER BY mukey"),
        ("component", "SELECT * FROM component " + f"WHERE mukey IN ({in_clause}) ORDER BY mukey, cokey"),
    )
    requests = []
    for role, sql in sqls:
        requests.append({
            "provider_id": "SSURGO_SOILS",
            "request_role": role,
            "identity_state": "DEPENDENT_PRODUCTION_ACQUISITION",
            "protocol": "SDA_TABULAR",
            "method": "POST",
            "url": SDA_TABULAR_ENDPOINT,
            "media_type": "application/json",
            "json_body": {"query": sql, "format": "JSON+COLUMNNAME"},
            "parent_denominator": {"key": "mukey", "count": len(mukeys), "canonical_set_sha256": canonical_mukey_sha256(mukeys)},
        })
    return {
        "schema_version": "spiderweb.ssurgo_stage2_plan.v1.0",
        "query": dict(query, mode="fetch"),
        "provider_denominator_count": 1,
        "route_state_counts": {"ROUTABLE": 1},
        "providers": [{"provider_id": "SSURGO_SOILS", "family": "soils", "status": "RESOLVER_ONLY", "route_state": "DEPENDENT_STAGE_ROUTABLE", "reason": "MapunitPoly MUKEY denominator frozen; tabular production acquisition may proceed"}],
        "request_count": len(requests),
        "requests": requests,
        "fetch_gate": "READY",
        "ssurgo_denominator": {"mukey_count": len(mukeys), "mukeys": mukeys, "canonical_mukey_set_sha256": canonical_mukey_sha256(mukeys), "mapunitpoly_raw_sha256": actual_raw_sha, "historical_equivalence": "UNRESOLVED"},
        "policy": {"plan_before_download": True, "raw_bytes_before_derivation": True, "whole_rows_preserved": True, "one_to_n_flattening": False, "count_equality_used_as_identity": False},
    }


def write_stage2_plan(*, query: dict[str, Any], mapunitpoly_raw_path: Path, mapunitpoly_receipt_path: Path, output: Path) -> dict[str, Any]:
    raw = mapunitpoly_raw_path.read_bytes()
    receipt = json.loads(mapunitpoly_receipt_path.read_text(encoding="utf-8"))
    plan = build_stage2_plan(query=query, mapunitpoly_raw=raw, mapunitpoly_receipt=receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan


def extract_cokeys_from_sda(raw: bytes) -> tuple[list[str], list[str]]:
    if not raw:
        raise SSURGOChainError("component raw bytes are empty")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SSURGOChainError(f"component JSON parse failure: {exc}") from exc
    table = obj.get("Table") if isinstance(obj, dict) else None
    if not isinstance(table, list) or len(table) < 1:
        raise SSURGOChainError("component response lacks Table")
    header = table[0]
    rows = table[1:]
    if not isinstance(header, list) or any(not isinstance(v, str) for v in header):
        raise SSURGOChainError("component header malformed")
    if "mukey" not in header or "cokey" not in header:
        raise SSURGOChainError("component response lacks mukey/cokey")
    mukey_idx = header.index("mukey")
    cokey_idx = header.index("cokey")
    cokeys: list[str] = []
    for row_number, row in enumerate(rows, 1):
        if not isinstance(row, list) or len(row) != len(header):
            raise SSURGOChainError(f"component row-width mismatch at row {row_number}")
        mukey = "" if row[mukey_idx] is None else str(row[mukey_idx]).strip()
        cokey = "" if row[cokey_idx] is None else str(row[cokey_idx]).strip()
        if not mukey or not mukey.isdigit():
            raise SSURGOChainError(f"component invalid MUKEY at row {row_number}")
        if not cokey or not cokey.isdigit():
            raise SSURGOChainError(f"component invalid COKEY at row {row_number}")
        cokeys.append(cokey)
    if not cokeys:
        raise SSURGOChainError("component response contains zero COKEY rows")
    if len(cokeys) != len(set(cokeys)):
        raise SSURGOChainError("component response contains duplicate COKEYs")
    return sorted(cokeys, key=int), header


def canonical_cokey_sha256(cokeys: list[str]) -> str:
    return sha256_bytes(("\n".join(cokeys) + "\n").encode("utf-8"))


def build_stage3_child_plan(
    *,
    query: dict[str, Any],
    component_raw: bytes,
    component_receipt: dict[str, Any],
    child_contract: dict[str, Any],
) -> dict[str, Any]:
    if component_receipt.get("provider_id") != "SSURGO_SOILS":
        raise SSURGOChainError("component receipt provider_id is not SSURGO_SOILS")
    if component_receipt.get("request_role") != "component":
        raise SSURGOChainError("component receipt request_role is not component")
    if component_receipt.get("state") != "PASS":
        raise SSURGOChainError("component acquisition receipt is not PASS")
    actual_sha = sha256_bytes(component_raw)
    if component_receipt.get("sha256") != actual_sha:
        raise SSURGOChainError("component raw SHA256 does not match receipt")

    cokeys, component_header = extract_cokeys_from_sda(component_raw)
    if child_contract.get("schema_version") != "spiderweb.ssurgo_component_children.v1.1":
        raise SSURGOChainError(
            "unsupported component child contract schema_version"
        )
    if child_contract.get("parent_table") != "component" or child_contract.get("parent_key") != "cokey":
        raise SSURGOChainError("component child contract parent binding drift")
    records = child_contract.get("records")
    if not isinstance(records, list) or not records:
        raise SSURGOChainError("component child contract lacks records")
    expected_count = child_contract.get("relationship_count")
    if expected_count != len(records):
        raise SSURGOChainError("component child contract relationship_count invariant drift")

    contract_bytes = json.dumps(
        child_contract,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    child_contract_sha = sha256_bytes(contract_bytes)

    seen_tables: set[str] = set()
    seen_stable_keys: set[str] = set()
    in_clause = _quoted_in(cokeys)
    requests: list[dict[str, Any]] = []

    for row in records:
        if not isinstance(row, dict):
            raise SSURGOChainError("component child contract contains non-object")
        table = str(row.get("table", "")).strip()
        stable_key = str(row.get("stable_key", "")).strip()
        parent_key = str(row.get("parent_key", "")).strip()
        if not table or not stable_key or parent_key != "cokey":
            raise SSURGOChainError(f"malformed component child contract row: {row!r}")
        if table in seen_tables:
            raise SSURGOChainError(f"duplicate child table in contract: {table}")
        if stable_key in seen_stable_keys:
            raise SSURGOChainError(f"duplicate child stable key in contract: {stable_key}")
        seen_tables.add(table)
        seen_stable_keys.add(stable_key)
        sql = (
            f"SELECT * FROM {table} "
            f"WHERE cokey IN ({in_clause}) "
            f"ORDER BY cokey, {stable_key}"
        )
        requests.append({
            "provider_id": "SSURGO_SOILS",
            "request_role": f"component_child:{table}",
            "identity_state": "DEPENDENT_PRODUCTION_ACQUISITION",
            "protocol": "SDA_TABULAR",
            "method": "POST",
            "url": SDA_TABULAR_ENDPOINT,
            "media_type": "application/json",
            "json_body": {"query": sql, "format": "JSON+COLUMNNAME"},
            "parent_denominator_sha256": canonical_cokey_sha256(cokeys),
            "ssurgo_child_contract_sha256": child_contract_sha,
            "ssurgo_child_contract": {
                "table": table,
                "parent_key": "cokey",
                "stable_key": stable_key,
                "key_evidence": row.get("key_evidence"),
                "cardinality": row.get("cardinality"),
            },
        })

    return {
        "schema_version": "spiderweb.ssurgo_stage3_child_plan.v1.0",
        "query": dict(query, mode="fetch"),
        "fetch_gate": "READY",
        "provider_denominator_count": 1,
        "route_state_counts": {"DEPENDENT_STAGE_ROUTABLE": 1},
        "providers": [{
            "provider_id": "SSURGO_SOILS",
            "family": "soils",
            "status": "RESOLVER_ONLY",
            "route_state": "DEPENDENT_STAGE_ROUTABLE",
        }],
        "request_count": len(requests),
        "requests": requests,
        "component_parent": {
            "raw_sha256": actual_sha,
            "runtime_schema_columns": len(component_header),
            "row_count": len(cokeys),
        },
        "ssurgo_cokey_denominator": {
            "cokey_count": len(cokeys),
            "cokeys": cokeys,
            "canonical_cokey_set_sha256": canonical_cokey_sha256(cokeys),
        },
        "child_table_denominator": {
            "schema_version": child_contract.get("schema_version"),
            "canonical_contract_sha256": child_contract_sha,
            "table_count": len(records),
            "tables": [request["ssurgo_child_contract"] for request in requests],
            "documentation_epoch": child_contract.get("current_documentation_epoch"),
            "prior_frozen_count": (child_contract.get("lineage") or {}).get("prior_frozen_relationship_count"),
            "historical_21_table_equivalence": "SUPERSEDED_FOR_CURRENT_DENOMINATOR",
        },
        "policy": {
            "whole_rows_preserved": True,
            "one_to_n_flattening": False,
            "zero_child_parent_is_failure": False,
            "count_equality_used_as_identity": False,
            "stable_child_key_required": True,
        },
    }


def certify_child_table_response(
    *,
    raw: bytes,
    receipt: dict[str, Any],
    contract: dict[str, Any],
    certified_cokeys: list[str],
) -> dict[str, Any]:
    table = str(contract.get("table", "")).strip()
    parent_key = str(contract.get("parent_key", "")).strip()
    stable_key = str(contract.get("stable_key", "")).strip()
    if not table or parent_key != "cokey" or not stable_key:
        raise SSURGOChainError("malformed child-table contract")
    if any(not value.isdigit() for value in certified_cokeys):
        raise SSURGOChainError("certified COKEY denominator contains non-numeric value")
    if len(certified_cokeys) != len(set(certified_cokeys)):
        raise SSURGOChainError("certified COKEY denominator contains duplicates")
    expected_parent_sha = canonical_cokey_sha256(certified_cokeys)

    if receipt.get("provider_id") != "SSURGO_SOILS":
        raise SSURGOChainError(f"{table}: receipt provider mismatch")
    if receipt.get("request_role") != f"component_child:{table}":
        raise SSURGOChainError(f"{table}: receipt role mismatch")
    if receipt.get("state") != "PASS":
        raise SSURGOChainError(f"{table}: acquisition receipt is not PASS")
    actual_sha = sha256_bytes(raw)
    if receipt.get("sha256") != actual_sha:
        raise SSURGOChainError(f"{table}: raw SHA256 does not match receipt")
    if receipt.get("parent_denominator_sha256") != expected_parent_sha:
        raise SSURGOChainError(f"{table}: parent COKEY denominator hash mismatch")

    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SSURGOChainError(f"{table}: response JSON parse failure: {exc}") from exc
    payload = obj.get("Table") if isinstance(obj, dict) else None
    if not isinstance(payload, list) or not payload:
        raise SSURGOChainError(f"{table}: response lacks Table")
    header = payload[0]
    rows = payload[1:]
    if not isinstance(header, list) or any(not isinstance(v, str) for v in header):
        raise SSURGOChainError(f"{table}: malformed header")
    if parent_key not in header or stable_key not in header:
        raise SSURGOChainError(f"{table}: parent/stable key missing from runtime schema")

    parent_idx = header.index(parent_key)
    stable_idx = header.index(stable_key)
    expected_parent_set = set(certified_cokeys)
    returned_parents: list[str] = []
    stable_values: list[str] = []

    for row_number, row in enumerate(rows, 1):
        if not isinstance(row, list) or len(row) != len(header):
            raise SSURGOChainError(f"{table}: row-width mismatch at row {row_number}")
        parent = "" if row[parent_idx] is None else str(row[parent_idx]).strip()
        stable = "" if row[stable_idx] is None else str(row[stable_idx]).strip()
        if not parent or not parent.isdigit():
            raise SSURGOChainError(f"{table}: invalid parent COKEY at row {row_number}")
        if parent not in expected_parent_set:
            raise SSURGOChainError(f"{table}: foreign parent COKEY {parent}")
        if not stable:
            raise SSURGOChainError(f"{table}: null/empty stable key at row {row_number}")
        returned_parents.append(parent)
        stable_values.append(stable)

    if len(stable_values) != len(set(stable_values)):
        raise SSURGOChainError(f"{table}: duplicate stable keys")

    counts = {value: 0 for value in certified_cokeys}
    for parent in returned_parents:
        counts[parent] += 1
    if sum(counts.values()) != len(rows):
        raise SSURGOChainError(f"{table}: parent-child arithmetic closure failed")

    zero = sorted((key for key, count in counts.items() if count == 0), key=int)
    one = sorted((key for key, count in counts.items() if count == 1), key=int)
    multi = sorted((key for key, count in counts.items() if count > 1), key=int)
    return {
        "schema_version": "spiderweb.ssurgo_child_table_certification.v1.0",
        "provider_id": "SSURGO_SOILS",
        "table": table,
        "state": "PASS",
        "raw_sha256": actual_sha,
        "parent_denominator_sha256": expected_parent_sha,
        "parent_key": parent_key,
        "stable_key": stable_key,
        "runtime_schema_columns": len(header),
        "row_count": len(rows),
        "unique_stable_keys": len(stable_values),
        "certified_parent_count": len(certified_cokeys),
        "returned_parent_count": len(set(returned_parents)),
        "foreign_parent_count": 0,
        "zero_child_parent_count": len(zero),
        "one_child_parent_count": len(one),
        "multi_child_parent_count": len(multi),
        "zero_child_parent_keys": zero,
        "arithmetic_closure": sum(counts.values()) == len(rows),
        "stable_key_uniqueness": len(stable_values) == len(set(stable_values)),
        "policy": {
            "zero_child_parent_is_not_failure_by_default": True,
            "one_to_n_preserved": True,
            "whole_rows_preserved_in_raw_bytes": True,
            "count_equality_used_as_identity": False,
        },
    }
