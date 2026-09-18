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
