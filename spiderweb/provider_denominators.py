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

    scope_raw = request_role.split(":", 1)[1] if request_role.startswith("folder_services:") else ""
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in services:
        if not isinstance(item, dict):
            raise DenominatorError("services contains non-object")
        name = item.get("name")
        service_type = item.get("type")
        if not isinstance(name, str) or not name.strip():
            raise DenominatorError("service has empty name")
        if not isinstance(service_type, str) or not service_type.strip():
            raise DenominatorError(f"service {name!r} has empty type")
        key = (scope_raw, name, service_type)
        if key in seen:
            raise DenominatorError(f"duplicate service manifestation: {key!r}")
        seen.add(key)
        records.append({"scope_raw": scope_raw, "name_raw": name, "type_raw": service_type})

    records.sort(key=lambda row: (row["scope_raw"].casefold(), row["name_raw"].casefold(), row["type_raw"].casefold()))
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
        "scope_raw": scope_raw,
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


def merge_arcgis_service_denominators(
    denominators: list[dict[str, Any]],
    *,
    provider_id: str,
) -> dict[str, Any]:
    if not denominators:
        raise DenominatorError("no service denominators supplied")
    records: list[dict[str, str]] = []
    folders: set[str] = set()
    parent_hashes: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for denominator in denominators:
        if denominator.get("state") != "PASS":
            raise DenominatorError("child service denominator is not PASS")
        if denominator.get("provider_id") != provider_id:
            raise DenominatorError("child service denominator provider mismatch")
        if denominator.get("schema_version") != "spiderweb.arcgis_service_denominator.v1.0":
            raise DenominatorError("unexpected service denominator schema")
        parent_hash = denominator.get("canonical_records_sha256")
        if not isinstance(parent_hash, str) or not parent_hash:
            raise DenominatorError("service denominator lacks canonical hash")
        parent_hashes.append(parent_hash)

        for folder in denominator.get("folders", []):
            if not isinstance(folder, str):
                raise DenominatorError("folder manifestation is not a string")
            folders.add(folder)

        child_records = denominator.get("records")
        if not isinstance(child_records, list):
            raise DenominatorError("service denominator lacks records")
        for record in child_records:
            if not isinstance(record, dict):
                raise DenominatorError("service denominator record is not object")
            scope = str(record.get("scope_raw", ""))
            name = record.get("name_raw")
            service_type = record.get("type_raw")
            if not isinstance(name, str) or not isinstance(service_type, str):
                raise DenominatorError("service denominator record malformed")
            key = (scope, name, service_type)
            if key in seen:
                raise DenominatorError(f"duplicate service across denominators: {key!r}")
            seen.add(key)
            records.append({"scope_raw": scope, "name_raw": name, "type_raw": service_type})

    records.sort(key=lambda row: (row["scope_raw"].casefold(), row["name_raw"].casefold(), row["type_raw"].casefold()))
    folder_records = sorted(folders, key=str.casefold)
    parent_hashes.sort()
    return {
        "schema_version": "spiderweb.arcgis_service_denominator_merged.v1.0",
        "provider_id": provider_id,
        "state": "PASS",
        "denominator_count": len(denominators),
        "service_count": len(records),
        "folder_count": len(folder_records),
        "folders": folder_records,
        "records": records,
        "parent_denominator_hashes": parent_hashes,
        "canonical_records_sha256": canonical_records_sha256(records),
        "identity_scope": "SOURCE_SERVICE_MANIFESTATIONS_WITH_FOLDER_SCOPE",
    }


def freeze_arcgis_service_contents_denominator(
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
        raise DenominatorError(f"ArcGIS service metadata JSON parse failure: {exc}") from exc

    source_binding = receipt.get("source_binding") or {}
    if not isinstance(source_binding, dict):
        raise DenominatorError("receipt source_binding is malformed")
    service_name = source_binding.get("service_name_raw")
    service_scope = source_binding.get("service_scope_raw", "")
    service_type = source_binding.get("service_type_raw")
    if service_name is not None and not isinstance(service_name, str):
        raise DenominatorError("service_name_raw in receipt is malformed")
    if not isinstance(service_scope, str):
        raise DenominatorError("service_scope_raw in receipt is malformed")
    if service_type is not None and not isinstance(service_type, str):
        raise DenominatorError("service_type_raw in receipt is malformed")

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for kind, key in (("layer", "layers"), ("table", "tables")):
        values = payload.get(key) or []
        if not isinstance(values, list):
            raise DenominatorError(f"ArcGIS service metadata {key} is not a list")
        for item in values:
            if not isinstance(item, dict):
                raise DenominatorError(f"ArcGIS service {key} contains non-object")
            object_id = item.get("id")
            name = item.get("name")
            if isinstance(object_id, bool) or not isinstance(object_id, int):
                raise DenominatorError(f"invalid ArcGIS {kind} id: {object_id!r}")
            if not isinstance(name, str) or not name.strip():
                raise DenominatorError(f"ArcGIS {kind} {object_id} has empty name")
            identity = (kind, object_id)
            if identity in seen:
                raise DenominatorError(f"duplicate ArcGIS service content identity: {identity!r}")
            seen.add(identity)
            records.append({
                "kind": kind,
                "id": object_id,
                "name_raw": name,
                "parent_layer_id": item.get("parentLayerId"),
                "default_visibility": item.get("defaultVisibility"),
                "sub_layer_ids": item.get("subLayerIds"),
            })

    records.sort(key=lambda row: (row["kind"], row["id"]))
    layer_count = sum(row["kind"] == "layer" for row in records)
    table_count = sum(row["kind"] == "table" for row in records)
    return {
        "schema_version": "spiderweb.arcgis_service_contents_denominator.v1.0",
        "provider_id": provider_id,
        "request_role": request_role,
        "state": "PASS",
        "raw_sha256": raw_sha,
        "service_scope_raw": service_scope,
        "service_name_raw": service_name,
        "service_type_raw": service_type,
        "record_count": len(records),
        "layer_count": layer_count,
        "table_count": table_count,
        "records": records,
        "canonical_records_sha256": canonical_records_sha256(records),
        "identity_scope": "SOURCE_SERVICE_LAYER_AND_TABLE_MANIFESTATIONS",
        "policy": {
            "table_manifestations_preserved": True,
            "name_only_identity": False,
            "identity_key": ["kind", "id"],
        },
    }


def merge_arcgis_service_contents_denominators(
    denominators: list[dict[str, Any]],
    *,
    provider_id: str,
) -> dict[str, Any]:
    if not denominators:
        raise DenominatorError("no service-content denominators supplied")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, int]] = set()
    parent_hashes: list[str] = []

    for denominator in denominators:
        if denominator.get("state") != "PASS":
            raise DenominatorError("service-content denominator is not PASS")
        if denominator.get("provider_id") != provider_id:
            raise DenominatorError("service-content denominator provider mismatch")
        if denominator.get("schema_version") != "spiderweb.arcgis_service_contents_denominator.v1.0":
            raise DenominatorError("unexpected service-content denominator schema")
        canonical = denominator.get("canonical_records_sha256")
        if not isinstance(canonical, str) or not canonical:
            raise DenominatorError("service-content denominator lacks canonical hash")
        parent_hashes.append(canonical)

        scope = str(denominator.get("service_scope_raw", ""))
        service = str(denominator.get("service_name_raw", ""))
        service_type = str(denominator.get("service_type_raw", ""))
        child_records = denominator.get("records")
        if not isinstance(child_records, list):
            raise DenominatorError("service-content denominator lacks records")

        for child in child_records:
            if not isinstance(child, dict):
                raise DenominatorError("service-content child is not object")
            kind = child.get("kind")
            object_id = child.get("id")
            if kind not in {"layer", "table"} or isinstance(object_id, bool) or not isinstance(object_id, int):
                raise DenominatorError("service-content child identity malformed")
            identity = (scope, service, service_type, kind, object_id)
            if identity in seen:
                raise DenominatorError(f"duplicate enterprise service content identity: {identity!r}")
            seen.add(identity)
            records.append({
                "service_scope_raw": scope,
                "service_name_raw": service,
                "service_type_raw": service_type,
                **child,
            })

    records.sort(
        key=lambda row: (
            row["service_scope_raw"].casefold(),
            row["service_name_raw"].casefold(),
            row["service_type_raw"].casefold(),
            row["kind"],
            row["id"],
        )
    )
    parent_hashes.sort()
    return {
        "schema_version": "spiderweb.arcgis_service_contents_denominator_merged.v1.0",
        "provider_id": provider_id,
        "state": "PASS",
        "denominator_count": len(denominators),
        "record_count": len(records),
        "layer_count": sum(row["kind"] == "layer" for row in records),
        "table_count": sum(row["kind"] == "table" for row in records),
        "records": records,
        "parent_denominator_hashes": parent_hashes,
        "canonical_records_sha256": canonical_records_sha256(records),
        "identity_scope": "ENTERPRISE_SOURCE_SERVICE_LAYER_AND_TABLE_MANIFESTATIONS",
    }
