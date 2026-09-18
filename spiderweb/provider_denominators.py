"""Deterministic denominator freezing for LOCATION_QUERY discovery metadata.

These parsers consume already-preserved provider metadata bytes plus acquisition
receipts. They never fetch network resources themselves and never promote a
metadata discovery object to canonical real-world identity.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Any


class DenominatorError(ValueError):
    """Fail-closed metadata denominator error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify(raw: bytes, receipt: dict[str, Any], provider_id: str, role: str) -> str:
    if not raw:
        raise DenominatorError("raw metadata bytes are empty")
    if receipt.get("provider_id") != provider_id:
        raise DenominatorError(f"receipt provider mismatch: {receipt.get('provider_id')!r}")
    if receipt.get("request_role") != role:
        raise DenominatorError(f"receipt role mismatch: {receipt.get('request_role')!r}")
    if receipt.get("state") != "PASS":
        raise DenominatorError("metadata acquisition receipt is not PASS")
    actual = sha256_bytes(raw)
    if receipt.get("sha256") != actual:
        raise DenominatorError("raw metadata SHA256 does not match receipt")
    return actual


def canonical_records_sha256(records: list[dict[str, Any]]) -> str:
    body = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(body)


def freeze_arcgis_layer_denominator(
    *,
    raw: bytes,
    receipt: dict[str, Any],
    provider_id: str,
    request_role: str,
) -> dict[str, Any]:
    raw_sha = _verify(raw, receipt, provider_id, request_role)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DenominatorError(f"ArcGIS metadata JSON parse failure: {exc}") from exc

    layers = payload.get("layers")
    if not isinstance(layers, list):
        raise DenominatorError("ArcGIS metadata lacks layers list")

    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in layers:
        if not isinstance(item, dict):
            raise DenominatorError("ArcGIS layers contains non-object")
        layer_id = item.get("id")
        name = item.get("name")
        if isinstance(layer_id, bool) or not isinstance(layer_id, int):
            raise DenominatorError(f"invalid ArcGIS layer id: {layer_id!r}")
        if layer_id in seen:
            raise DenominatorError(f"duplicate ArcGIS layer id: {layer_id}")
        if not isinstance(name, str) or not name.strip():
            raise DenominatorError(f"layer {layer_id} has empty name")
        seen.add(layer_id)
        records.append({
            "layer_id": layer_id,
            "name_raw": name,
            "parent_layer_id": item.get("parentLayerId"),
            "default_visibility": item.get("defaultVisibility"),
            "sub_layer_ids": item.get("subLayerIds"),
        })

    records.sort(key=lambda row: row["layer_id"])
    return {
        "schema_version": "spiderweb.arcgis_layer_denominator.v1.0",
        "provider_id": provider_id,
        "request_role": request_role,
        "state": "PASS",
        "raw_sha256": raw_sha,
        "layer_count": len(records),
        "layer_ids_unique": len(records) == len({row["layer_id"] for row in records}),
        "records": records,
        "canonical_records_sha256": canonical_records_sha256(records),
        "identity_scope": "SOURCE_LAYER_MANIFESTATIONS",
    }


def freeze_arcgis_service_denominator(
    *,
    raw: bytes,
    receipt: dict[str, Any],
    provider_id: str,
    request_role: str,
) -> dict[str, Any]:
    raw_sha = _verify(raw, receipt, provider_id, request_role)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DenominatorError(f"ArcGIS service-root JSON parse failure: {exc}") from exc

    services = payload.get("services")
    if not isinstance(services, list):
        raise DenominatorError("ArcGIS service root lacks services list")

    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in services:
        if not isinstance(item, dict):
            raise DenominatorError("services contains non-object")
        name = item.get("name")
        service_type = item.get("type")
        if not isinstance(name, str) or not name.strip():
            raise DenominatorError("service has empty name")
        if not isinstance(service_type, str) or not service_type.strip():
            raise DenominatorError(f"service {name!r} has empty type")
        key = (name, service_type)
        if key in seen:
            raise DenominatorError(f"duplicate service manifestation: {key!r}")
        seen.add(key)
        records.append({"name_raw": name, "type_raw": service_type})

    records.sort(key=lambda row: (row["name_raw"].casefold(), row["type_raw"].casefold()))
    folders = payload.get("folders")
    if folders is None:
        folders = []
    if not isinstance(folders, list) or any(not isinstance(value, str) for value in folders):
        raise DenominatorError("folders is not a string list")
    folder_records = sorted(set(folders), key=str.casefold)

    return {
        "schema_version": "spiderweb.arcgis_service_denominator.v1.0",
        "provider_id": provider_id,
        "request_role": request_role,
        "state": "PASS",
        "raw_sha256": raw_sha,
        "service_count": len(records),
        "folder_count": len(folder_records),
        "records": records,
        "folders": folder_records,
        "canonical_records_sha256": canonical_records_sha256(records),
        "identity_scope": "SOURCE_SERVICE_MANIFESTATIONS",
    }


def freeze_wms_layer_denominator(
    *,
    raw: bytes,
    receipt: dict[str, Any],
    provider_id: str,
    request_role: str,
) -> dict[str, Any]:
    raw_sha = _verify(raw, receipt, provider_id, request_role)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise DenominatorError(f"WMS capabilities XML parse failure: {exc}") from exc

    records: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for layer in root.iter():
        if layer.tag.rsplit("}", 1)[-1] != "Layer":
            continue
        name = None
        title = None
        for child in list(layer):
            local = child.tag.rsplit("}", 1)[-1]
            if local == "Name" and name is None:
                name = (child.text or "").strip() or None
            elif local == "Title" and title is None:
                title = (child.text or "").strip() or None
        if name is None:
            continue
        if name in seen:
            raise DenominatorError(f"duplicate WMS layer Name: {name}")
        seen.add(name)
        records.append({"name_raw": name, "title_raw": title})

    if not records:
        raise DenominatorError("WMS capabilities yielded zero named layers")
    records.sort(key=lambda row: str(row["name_raw"]).casefold())
    return {
        "schema_version": "spiderweb.wms_layer_denominator.v1.0",
        "provider_id": provider_id,
        "request_role": request_role,
        "state": "PASS",
        "raw_sha256": raw_sha,
        "layer_count": len(records),
        "records": records,
        "canonical_records_sha256": canonical_records_sha256(records),
        "identity_scope": "SOURCE_WMS_LAYER_MANIFESTATIONS",
    }
