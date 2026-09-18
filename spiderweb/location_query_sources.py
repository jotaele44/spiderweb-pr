"""Provider-specific request planning for Spiderweb LOCATION_QUERY.

This module does not perform network I/O. It converts a validated LOCATION_QUERY
into bounded request specifications for authoritative machine-readable provider
surfaces. Execution is handled by scripts/location_query_fetch.py so planning,
source identity, transfer, and certification remain separate states.
"""
from __future__ import annotations

from math import cos, radians
from typing import Any
from urllib.parse import urlencode

PR_DEG_LAT_M = 111_320.0

def _iter_coords(value: Any):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for child in value:
                yield from _iter_coords(child)

def _geojson_coords(value: Any):
    if not isinstance(value, dict):
        return
    kind = value.get("type")
    if kind == "Feature":
        yield from _geojson_coords(value.get("geometry") or {})
    elif kind == "FeatureCollection":
        for feature in value.get("features") or []:
            yield from _geojson_coords(feature)
    else:
        yield from _iter_coords(value.get("coordinates"))

def query_bbox(query: dict[str, Any]) -> tuple[float, float, float, float]:
    g = query["geometry"]
    kind = g["type"]
    if kind == "bbox":
        return float(g["west"]), float(g["south"]), float(g["east"]), float(g["north"])
    if kind == "point":
        lon, lat = float(g["lon"]), float(g["lat"])
        epsilon = 1e-7
        return lon - epsilon, lat - epsilon, lon + epsilon, lat + epsilon
    if kind == "radius":
        lon, lat, r = float(g["lon"]), float(g["lat"]), float(g["radius_m"])
        dy = r / PR_DEG_LAT_M
        dx = r / (PR_DEG_LAT_M * max(0.01, cos(radians(lat))))
        return lon - dx, lat - dy, lon + dx, lat + dy
    gj = g["geojson"]
    coords = list(_geojson_coords(gj))
    if not coords:
        raise ValueError("GeoJSON geometry has no numeric coordinates")
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    return min(xs), min(ys), max(xs), max(ys)

def _arcgis_query(url: str, bbox: tuple[float, float, float, float], *, out_fields: str = "*") -> dict[str, Any]:
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
    layer_url = url.rstrip("/")
    return {
        "protocol": "ARCGIS_FEATURE_LAYER",
        "method": "GET",
        "url": layer_url + "/query?" + urlencode(params),
        "layer_url": layer_url,
        "bbox_wgs84": list(bbox),
        "out_fields": out_fields,
        "media_type": "application/json",
        "pagination_policy": "OBJECT_ID_DENOMINATOR_THEN_BATCH",
    }

def _wfs_getfeature(base: str, typename: str, bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": typename,
        "BBOX": f"{west},{south},{east},{north},EPSG:4326",
    }
    return {"method": "GET", "url": base + "?" + urlencode(params), "media_type": "application/gml+xml"}


def _ogc_items(url: str, bbox: tuple[float, float, float, float], extra: dict[str, str] | None = None) -> dict[str, Any]:
    west, south, east, north = bbox
    params = {"bbox": f"{west},{south},{east},{north}", "f": "json"}
    if extra:
        params.update(extra)
    joiner = "&" if "?" in url else "?"
    return {"method": "GET", "url": url + joiner + urlencode(params), "media_type": "application/geo+json"}

def _subsurface_specs(provider_id: str, family: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    # Reuse the existing frozen source denominator instead of duplicating URLs.
    from spiderweb.subsurface.sources import DEFAULT_SOURCES, SourceKind, SourceStatus

    rows: list[dict[str, Any]] = []
    for source in DEFAULT_SOURCES:
        if source.family != family or source.status != SourceStatus.VERIFIED_QUERYABLE:
            continue
        if source.kind == SourceKind.ARCGIS_LAYER:
            row = _arcgis_query(f"{source.endpoint.rstrip('/')}/{source.layer_id}", bbox)
        elif source.kind == SourceKind.OGC_FEATURES:
            row = _ogc_items(source.endpoint, bbox, source.query_dict)
        else:
            continue
        row.update({
            "provider_id": provider_id,
            "request_role": source.source_id,
            "identity_state": "SOURCE_MANIFESTATION",
            "stable_id_fields": list(source.stable_id_fields),
            "evidence_role": source.evidence_role,
        })
        rows.append(row)
    return rows

def build_request_specs(provider_id: str, provider: dict[str, Any], query: dict[str, Any]) -> list[dict[str, Any]]:
    bbox = query_bbox(query)
    specs: list[dict[str, Any]] = []


    if provider_id == "PRPB_GEOLOGY_KARST":
        return _subsurface_specs(provider_id, "GEOLOGY_KARST_CAVES", bbox)

    if provider_id == "PR_AQUIFERS_WELLS_SPRINGS":
        return _subsurface_specs(provider_id, "AQUIFERS_WELLS_SPRINGS", bbox)

    if provider_id == "SSURGO_SOILS":
        base = provider["wfs_endpoint"]
        for typename in ("SurveyAreaPoly", "MapunitPoly"):
            row = _wfs_getfeature(base, typename, bbox)
            row.update({"provider_id": provider_id, "request_role": typename, "identity_state": "SOURCE_MANIFESTATION"})
            specs.append(row)
        return specs

    if provider_id == "USFWS_NWI":
        row = _arcgis_query(provider["layer_url"], bbox)
        row.update({
            "provider_id": provider_id,
            "request_role": "wetlands",
            "identity_state": "SOURCE_MANIFESTATION",
        })
        return [row]

    if provider_id == "USGS_3DHP_NHD":
        for item in provider["layers"]:
            row = _arcgis_query(
                f"{provider['feature_service'].rstrip('/')}/{int(item['id'])}",
                bbox,
            )
            row.update({
                "provider_id": provider_id,
                "request_role": item["role"],
                "identity_state": "SOURCE_MANIFESTATION",
                "source_lineage_state": "EDH_OR_NHD_AS_REPORTED_BY_3DHP",
            })
            specs.append(row)
        return specs

    if provider_id == "USACE_PORTS_NAV":
        for item in provider["layers"]:
            row = _arcgis_query(item["url"], bbox)
            row.update({"provider_id": provider_id, "request_role": item["role"], "identity_state": "SOURCE_MANIFESTATION"})
            specs.append(row)
        return specs

    if provider_id == "FEMA_NFHL":
        return [{
            "provider_id": provider_id,
            "request_role": "nfhl_wms_capabilities",
            "method": "GET",
            "url": provider["wms_capabilities"],
            "media_type": "application/xml",
            "bbox_wgs84": list(bbox),
            "identity_state": "RESOLVER_ONLY",
        }]

    if provider_id == "FEMA_PR_ABFE_1PCT":
        return [{
            "provider_id": provider_id,
            "request_role": "abfe_map_service_denominator",
            "method": "GET",
            "url": provider["map_service"].rstrip("/") + "?f=json",
            "media_type": "application/json",
            "bbox_wgs84": list(bbox),
            "identity_state": "DISCOVERY_FOR_LAYER_DENOMINATOR",
        }]

    return []
