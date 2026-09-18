"""Dependent metadata/query plans from frozen LOCATION_QUERY denominators.

A denominator receipt is authoritative only for the provider manifestation it
freezes. These helpers preserve that parent binding and emit the next bounded
request set without treating names, counts, or ordering as identity evidence.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from spiderweb.location_query_sources import query_bbox


class DenominatorChainError(ValueError):
    """Fail-closed dependent denominator planning error."""


def _require_pass(denominator: dict[str, Any], provider_id: str) -> None:
    if denominator.get("state") != "PASS":
        raise DenominatorChainError("parent denominator is not PASS")
    if denominator.get("provider_id") != provider_id:
        raise DenominatorChainError("parent denominator provider mismatch")
    if not denominator.get("canonical_records_sha256"):
        raise DenominatorChainError("parent denominator lacks canonical records hash")


def _arcgis_layer_request(
    layer_url: str,
    bbox: tuple[float, float, float, float],
    *,
    out_fields: str = "*",
) -> dict[str, Any]:
    west, south, east, north = bbox
    params = {
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnIdsOnly": "true",
        "f": "json",
    }
    normalized = layer_url.rstrip("/")
    return {
        "protocol": "ARCGIS_FEATURE_LAYER",
        "method": "GET",
        "url": normalized + "/query?" + urlencode(params),
        "layer_url": normalized,
        "bbox_wgs84": list(bbox),
        "out_fields": out_fields,
        "media_type": "application/json",
        "pagination_policy": "OBJECT_ID_DENOMINATOR_THEN_BATCH",
    }


def build_usace_service_metadata_plan(
    *,
    query: dict[str, Any],
    service_root: str,
    denominator: dict[str, Any],
) -> dict[str, Any]:
    provider_id = "USACE_GENERAL_GIS"
    _require_pass(denominator, provider_id)
    if denominator.get("schema_version") not in {
        "spiderweb.arcgis_service_denominator.v1.0",
        "spiderweb.arcgis_service_denominator_merged.v1.0",
    }:
        raise DenominatorChainError("USACE parent is not an ArcGIS service denominator")

    requests: list[dict[str, Any]] = []

    # First recurse into any folders that have not yet been independently frozen.
    for folder in denominator.get("folders", []):
        if not isinstance(folder, str) or not folder:
            raise DenominatorChainError("USACE folder manifestation is invalid")
        encoded_folder = "/".join(quote(part, safe="") for part in folder.split("/"))
        requests.append({
            "provider_id": provider_id,
            "request_role": f"folder_services:{folder}",
            "identity_state": "DEPENDENT_DISCOVERY_FOR_SERVICE_DENOMINATOR",
            "protocol": "ARCGIS_METADATA",
            "method": "GET",
            "url": f"{service_root.rstrip('/')}/{encoded_folder}?f=pjson",
            "media_type": "application/json",
            "parent_denominator_sha256": denominator["canonical_records_sha256"],
        })

    # Then request metadata for every map/feature service manifestation already
    # present in the frozen denominator. Scope is preserved separately from name.
    for record in denominator.get("records", []):
        if not isinstance(record, dict):
            raise DenominatorChainError("USACE denominator contains non-object record")
        scope = str(record.get("scope_raw", ""))
        name = record.get("name_raw")
        service_type = record.get("type_raw")
        if not isinstance(name, str) or not name:
            raise DenominatorChainError("USACE service record lacks name_raw")
        if service_type not in {"MapServer", "FeatureServer"}:
            continue

        path_parts = [part for part in scope.split("/") if part] + [part for part in name.split("/") if part]
        encoded_name = "/".join(quote(part, safe="") for part in path_parts)
        url = f"{service_root.rstrip('/')}/{encoded_name}/{service_type}?f=pjson"
        requests.append({
            "provider_id": provider_id,
            "request_role": f"service_metadata:{scope}:{name}:{service_type}",
            "identity_state": "DEPENDENT_DISCOVERY_FOR_LAYER_DENOMINATOR",
            "protocol": "ARCGIS_METADATA",
            "method": "GET",
            "url": url,
            "media_type": "application/json",
            "parent_denominator_sha256": denominator["canonical_records_sha256"],
            "service_scope_raw": scope,
            "service_name_raw": name,
            "service_type_raw": service_type,
        })

    return {
        "schema_version": "spiderweb.usace_service_metadata_plan.v1.1",
        "query": dict(query, mode="fetch"),
        "provider_denominator_count": 1,
        "route_state_counts": {"DEPENDENT_DISCOVERY": 1},
        "providers": [{
            "provider_id": provider_id,
            "family": "federal_infrastructure",
            "status": "RESOLVER_ONLY",
            "route_state": "DEPENDENT_DISCOVERY",
        }],
        "request_count": len(requests),
        "requests": requests,
        "fetch_gate": "READY",
        "parent_denominator": {
            "service_count": denominator.get("service_count"),
            "folder_count": denominator.get("folder_count", len(denominator.get("folders", []))),
            "canonical_records_sha256": denominator["canonical_records_sha256"],
        },
        "policy": {
            "folder_scope_preserved": True,
            "service_name_not_identity_alone": True,
            "recursive_folder_discovery_required": bool(denominator.get("folders")),
        },
    }


def build_arcgis_layer_aoi_plan(
    *,
    query: dict[str, Any],
    provider_id: str,
    service_url: str,
    denominator: dict[str, Any],
    role_prefix: str = "layer",
) -> dict[str, Any]:
    _require_pass(denominator, provider_id)
    if denominator.get("schema_version") != "spiderweb.arcgis_layer_denominator.v1.0":
        raise DenominatorChainError("parent is not an ArcGIS layer denominator")
    bbox = query_bbox(query)
    records = denominator.get("records")
    if not isinstance(records, list):
        raise DenominatorChainError("layer denominator records missing")

    requests: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise DenominatorChainError("layer denominator contains non-object")
        layer_id = record.get("layer_id")
        name = record.get("name_raw")
        if isinstance(layer_id, bool) or not isinstance(layer_id, int):
            raise DenominatorChainError("layer denominator has invalid layer_id")
        request = _arcgis_layer_request(
            f"{service_url.rstrip('/')}/{layer_id}",
            bbox,
        )
        request.update({
            "provider_id": provider_id,
            "request_role": f"{role_prefix}:{layer_id}:{name}",
            "identity_state": "SOURCE_LAYER_MANIFESTATION",
            "parent_denominator_sha256": denominator["canonical_records_sha256"],
            "layer_id": layer_id,
            "layer_name_raw": name,
        })
        requests.append(request)

    return {
        "schema_version": "spiderweb.arcgis_layer_aoi_plan.v1.0",
        "query": dict(query, mode="fetch"),
        "provider_denominator_count": 1,
        "route_state_counts": {"DEPENDENT_STAGE_ROUTABLE": 1},
        "providers": [{
            "provider_id": provider_id,
            "status": "RESOLVER_ONLY",
            "route_state": "DEPENDENT_STAGE_ROUTABLE",
        }],
        "request_count": len(requests),
        "requests": requests,
        "parent_denominator": {
            "layer_count": denominator.get("layer_count"),
            "canonical_records_sha256": denominator["canonical_records_sha256"],
        },
        "policy": {
            "count_equality_used_as_identity": False,
            "source_layer_identity_preserved": True,
            "no_coverage_is_not_source_absence": True,
        },
    }
