"""Discovery-only place-name resolver for Spiderweb.

Geocoding is intentionally upstream of LOCATION_QUERY. It returns a full
candidate set and never auto-promotes a name match to canonical geometry.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlencode


class PlaceResolverError(ValueError):
    """Fail-closed geocoder planning/parsing error."""


NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_place_discovery_plan(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise PlaceResolverError("place request must be an object")
    query_id = str(request.get("query_id", "")).strip()
    text = str(request.get("text", "")).strip()
    if not query_id or not text:
        raise PlaceResolverError("query_id and text are required")
    limit = request.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
        raise PlaceResolverError("limit must be integer 1..25")
    country_codes = request.get("country_codes", ["pr"])
    if not isinstance(country_codes, list) or any(not isinstance(v, str) or not v.strip() for v in country_codes):
        raise PlaceResolverError("country_codes must be a list of strings")
    params = {
        "q": text,
        "format": "jsonv2",
        "addressdetails": "1",
        "polygon_geojson": "1",
        "limit": str(limit),
        "countrycodes": ",".join(v.strip().lower() for v in country_codes),
    }
    url = NOMINATIM_SEARCH + "?" + urlencode(params)
    return {
        "schema_version": "spiderweb.place_discovery_plan.v1.0",
        "query": {"query_id": query_id, "text_raw": text, "limit": limit, "country_codes": country_codes, "mode": "fetch"},
        "provider_denominator_count": 1,
        "route_state_counts": {"DISCOVERY_ONLY": 1},
        "providers": [{
            "provider_id": "OSM_NOMINATIM_GEOCODER",
            "family": "place_geocoder",
            "status": "DISCOVERY_ONLY",
            "route_state": "DISCOVERY_ONLY",
        }],
        "request_count": 1,
        "requests": [{
            "provider_id": "OSM_NOMINATIM_GEOCODER",
            "request_role": "place_search",
            "identity_state": "CANDIDATE_NOT_IDENTITY",
            "method": "GET",
            "url": url,
            "media_type": "application/json",
        }],
        "policy": {
            "candidate_set_preserved": True,
            "name_only_identity_prohibited": True,
            "nearest_only_identity_prohibited": True,
            "automatic_candidate_selection": False,
            "location_query_requires_explicit_candidate_binding": True,
        },
    }


def parse_place_candidates(raw: bytes, receipt: dict[str, Any]) -> dict[str, Any]:
    if receipt.get("provider_id") != "OSM_NOMINATIM_GEOCODER":
        raise PlaceResolverError("geocoder receipt provider mismatch")
    if receipt.get("request_role") != "place_search" or receipt.get("state") != "PASS":
        raise PlaceResolverError("geocoder receipt is not a PASS place_search")
    actual = sha256_bytes(raw)
    if receipt.get("sha256") != actual:
        raise PlaceResolverError("geocoder raw SHA256 does not match receipt")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlaceResolverError(f"geocoder JSON parse failure: {exc}") from exc
    if not isinstance(payload, list):
        raise PlaceResolverError("geocoder response is not a list")

    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise PlaceResolverError("geocoder candidate is not an object")
        lat = item.get("lat")
        lon = item.get("lon")
        display_name = item.get("display_name")
        if not isinstance(lat, str) or not isinstance(lon, str) or not isinstance(display_name, str):
            raise PlaceResolverError("geocoder candidate lacks lat/lon/display_name")
        try:
            lat_f, lon_f = float(lat), float(lon)
        except ValueError as exc:
            raise PlaceResolverError("geocoder candidate has nonnumeric coordinates") from exc
        bbox_raw = item.get("boundingbox")
        bbox = None
        if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
            try:
                south, north, west, east = (float(v) for v in bbox_raw)
                bbox = {"west": west, "south": south, "east": east, "north": north}
            except (TypeError, ValueError):
                bbox = None
        candidates.append({
            "candidate_index": index,
            "state": "CANDIDATE_NOT_IDENTITY",
            "display_name_raw": display_name,
            "lat": lat_f,
            "lon": lon_f,
            "bbox": bbox,
            "place_id": item.get("place_id"),
            "osm_type": item.get("osm_type"),
            "osm_id": item.get("osm_id"),
            "category": item.get("category"),
            "type": item.get("type"),
            "importance": item.get("importance"),
            "geojson": item.get("geojson"),
        })

    return {
        "schema_version": "spiderweb.place_candidates.v1.0",
        "state": "PASS",
        "raw_sha256": actual,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "identity_state": "UNRESOLVED",
        "policy": {
            "full_candidate_set_preserved": True,
            "automatic_selection": False,
            "name_only_identity": False,
            "proximity_only_identity": False,
        },
    }


def bind_candidate_to_location_query(
    *,
    candidates: dict[str, Any],
    candidate_index: int,
    query_id: str,
    prefer_bbox: bool = True,
) -> dict[str, Any]:
    rows = candidates.get("candidates")
    if not isinstance(rows, list):
        raise PlaceResolverError("candidate artifact lacks candidates list")
    matches = [row for row in rows if row.get("candidate_index") == candidate_index]
    if len(matches) != 1:
        raise PlaceResolverError("candidate_index does not resolve uniquely")
    row = matches[0]
    if prefer_bbox and isinstance(row.get("bbox"), dict):
        geometry = {"type": "bbox", **row["bbox"]}
    else:
        geometry = {"type": "point", "lat": row["lat"], "lon": row["lon"]}
    return {
        "query_id": query_id,
        "geometry": geometry,
        "mode": "plan",
        "binding": {
            "source": "OSM_NOMINATIM_GEOCODER",
            "candidate_index": candidate_index,
            "candidate_state_before_binding": "CANDIDATE_NOT_IDENTITY",
            "binding_state": "ANALYST_EXPLICIT_SELECTION",
            "display_name_raw": row["display_name_raw"],
        },
    }
