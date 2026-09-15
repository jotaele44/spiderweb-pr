"""Frozen, read-only AOI planning. This module never downloads source assets.

The bounded denominator is the configured, hash-pinned GeoJSON tile-index
snapshot, not every provider dataset. Unsupported/unbound catalogs stay BLOCKED.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from shapely.geometry import box, mapping, shape
from shapely.ops import transform
from shapely.validation import explain_validity

MAX_BYTES = 5 * 1024 * 1024
MAX_CATALOG_BYTES = 64 * 1024 * 1024
MAX_VERTICES = 20000
MAX_ROWS = 50000
POLYGON_TYPES = {"Polygon", "MultiPolygon"}
CRS84 = {"EPSG:4326", "OGC:CRS84", "urn:ogc:def:crs:OGC:1.3:CRS84"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite JSON value: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def geometry_document(value: dict) -> dict:
    """Do not merge a FeatureCollection or silently select its first feature."""
    if not isinstance(value, dict):
        raise ValueError("AOI must be a GeoJSON object")
    if "crs" in value:
        crs = value["crs"]
        name = (crs.get("properties") or {}).get("name") if isinstance(crs, dict) else None
        if name not in CRS84:
            raise ValueError("unknown/non-WGS84 CRS; explicit conversion required")
    kind = value.get("type")
    if kind == "FeatureCollection":
        features = value.get("features")
        if not isinstance(features, list) or len(features) != 1:
            raise ValueError("FeatureCollection requires exactly one selected feature")
        return geometry_document(features[0])
    if kind == "Feature":
        return geometry_document(value.get("geometry"))
    if kind not in POLYGON_TYPES:
        raise ValueError("only Polygon/MultiPolygon AOIs are supported")
    return copy.deepcopy(value)


def valid_polygon(document: dict):
    geometry = geometry_document(document)
    polygons = ([geometry.get("coordinates")] if geometry["type"] == "Polygon"
                else geometry.get("coordinates"))
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("empty polygon")
    count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("empty polygon part")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("each ring requires at least four closed positions")
            if ring[0] != ring[-1]:
                raise ValueError("ring is not explicitly closed; no silent repair")
            for position in ring:
                if not isinstance(position, list) or len(position) != 2:
                    raise ValueError("positions must be 2D [longitude, latitude]; Z is not discarded")
                x, y = position
                if any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in position):
                    raise ValueError("coordinates must be finite numbers")
                if not -180 <= x <= 180 or not -90 <= y <= 90:
                    raise ValueError("coordinates outside CRS84 range")
            if any(abs(a[0] - b[0]) > 180 for a, b in zip(ring, ring[1:])):
                raise ValueError("antimeridian crossing requires explicit split")
            count += len(ring) - 1
            if count > MAX_VERTICES:
                raise ValueError("AOI vertex limit exceeded")
    result = shape(geometry)
    if result.is_empty or not result.is_valid or result.area <= 0:
        raise ValueError(f"invalid polygon: {explain_validity(result)}")
    if result.bounds[2] - result.bounds[0] > 180:
        raise ValueError("AOI longitude span exceeds supported regional scope")
    return geometry, result, count


def area_km2(geometry) -> float:
    # Optional geo extra supplies pyproj; absence is a failure, not invented area.
    from pyproj import Geod
    from shapely.geometry.polygon import orient

    geod = Geod(ellps="WGS84")
    parts = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    return sum(abs(geod.geometry_area_perimeter(orient(part, sign=1))[0])
               for part in parts) / 1_000_000


def processing_geometry(aoi, buffer_m: float):
    if buffer_m == 0:
        return aoi, {"method": "NONE", "buffer_m": 0}
    if not 0 < buffer_m <= 10000:
        raise ValueError("processing buffer must be 0–10000 metres")
    west, south, east, north = aoi.bounds
    # Bound the metric approximation to Puerto Rico, instead of buffering degrees.
    if not (-68 <= west <= east <= -64 and 17 <= south <= north <= 20):
        raise ValueError("metric buffer currently supported only within PR regional extent")
    from pyproj import Transformer

    forward = Transformer.from_crs("EPSG:4326", "EPSG:32620", always_xy=True)
    reverse = Transformer.from_crs("EPSG:32620", "EPSG:4326", always_xy=True)
    result = transform(reverse.transform, transform(forward.transform, aoi).buffer(buffer_m))
    if not result.is_valid:
        raise ValueError("invalid processing-buffer result")
    return result, {"method": "UTM20N_planar", "crs": "EPSG:32620",
                    "buffer_m": buffer_m, "quad_segs": 16}


def relation(aoi, footprint):
    intersection = aoi.intersection(footprint)
    if intersection.is_empty:
        return "OUTSIDE", None
    if intersection.area == 0:
        return "TOUCH_ONLY", mapping(intersection)
    return ("FULLY_WITHIN" if aoi.covers(footprint) else "PARTIAL"), mapping(intersection)


def safe_snapshot(root: Path, provider: dict) -> tuple[bytes, dict]:
    ref = provider.get("catalog_path")
    if not isinstance(ref, str) or not ref:
        raise ValueError("CATALOG_PATH_UNBOUND")
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("CATALOG_PATH_OUTSIDE_REPOSITORY")
    if provider.get("catalog_type") != "geojson":
        raise ValueError("CATALOG_ADAPTER_NOT_SUPPORTED: exact GeoJSON footprints required")
    if not path.is_file():
        raise ValueError("CATALOG_SNAPSHOT_UNAVAILABLE")
    if path.stat().st_size > MAX_CATALOG_BYTES:
        raise ValueError("CATALOG_BYTE_LIMIT")
    raw = path.read_bytes()
    expected = provider.get("catalog_sha256")
    actual = hashlib.sha256(raw).hexdigest()
    if not isinstance(expected, str) or expected.lower() != actual:
        raise ValueError("CATALOG_HASH_UNBOUND_OR_MISMATCH")
    doc = strict_json(raw)
    if not isinstance(doc, dict) or doc.get("type") != "FeatureCollection":
        raise ValueError("CATALOG_NOT_FEATURECOLLECTION")
    if "crs" in doc:
        crs = doc["crs"]
        if not isinstance(crs, dict) or (crs.get("properties") or {}).get("name") not in CRS84:
            raise ValueError("CATALOG_CRS_UNRESOLVED")
    features = doc.get("features")
    if not isinstance(features, list) or len(features) > MAX_ROWS:
        raise ValueError("CATALOG_ROW_LIMIT_OR_INVALID_FEATURES")
    expected_count = provider.get("catalog_record_count")
    if type(expected_count) is not int or expected_count != len(features):
        raise ValueError("CATALOG_RECORD_DENOMINATOR_UNBOUND_OR_MISMATCH")
    return raw, doc


def validate_filters(request: dict) -> dict:
    filters = request.get("filters", {})
    if not isinstance(filters, dict):
        raise ValueError("filters must be an object")
    allowed = {"products", "providers", "date_from", "date_to", "max_resolution_m"}
    if set(filters) - allowed:
        raise ValueError("unknown filter")
    for field in ("products", "providers"):
        value = filters.get(field, [])
        if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
            raise ValueError(f"{field} must be a string array")
    for field in ("date_from", "date_to"):
        if filters.get(field):
            date.fromisoformat(filters[field])
    if filters.get("date_from") and filters.get("date_to"):
        if filters["date_from"] > filters["date_to"]:
            raise ValueError("date_from exceeds date_to")
    resolution = filters.get("max_resolution_m")
    if resolution is not None and (isinstance(resolution, bool)
            or not isinstance(resolution, (float, int))
            or not math.isfinite(resolution) or resolution <= 0):
        raise ValueError("max_resolution_m must be positive")
    return copy.deepcopy(filters)


def filter_result(row: dict, filters: dict) -> tuple[str, list[str]]:
    excluded, unresolved = [], []
    for field, key in (("products", "product"), ("providers", "source")):
        if filters.get(field):
            if row[key] == "UNRESOLVED":
                unresolved.append(f"FILTER_{field.upper()}_UNKNOWN")
            elif row[key] not in filters[field]:
                excluded.append(f"FILTER_{field.upper()}")
    if filters.get("date_from") or filters.get("date_to"):
        value = row.get("acquisition_date")
        try:
            observed = date.fromisoformat(value)
        except (TypeError, ValueError):
            unresolved.append("FILTER_ACQUISITION_DATE_UNKNOWN")
        else:
            if filters.get("date_from") and observed < date.fromisoformat(filters["date_from"]):
                excluded.append("FILTER_DATE_FROM")
            if filters.get("date_to") and observed > date.fromisoformat(filters["date_to"]):
                excluded.append("FILTER_DATE_TO")
    maximum = filters.get("max_resolution_m")
    if maximum is not None:
        value = row.get("resolution_m")
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            unresolved.append("FILTER_RESOLUTION_UNKNOWN")
        elif value > maximum:
            excluded.append("FILTER_RESOLUTION")
    if excluded:
        return "EXCLUDED", excluded + unresolved
    if unresolved:
        return "UNRESOLVED", unresolved
    return "RETAINED", []


def build_plan(request: dict, registry: dict, root: Path) -> dict:
    allowed = {"aoi", "raw_import_text", "input_kind", "filters", "processing_buffer_m"}
    if not isinstance(request, dict) or set(request) - allowed or "aoi" not in request:
        raise ValueError("invalid plan request fields")
    canonical, aoi, vertex_count = valid_polygon(request["aoi"])
    buffer_m = request.get("processing_buffer_m", 0)
    if isinstance(buffer_m, bool) or not isinstance(buffer_m, (float, int)) or not math.isfinite(buffer_m):
        raise ValueError("buffer must be a finite number")
    processing, buffer_method = processing_geometry(aoi, buffer_m)
    filters = validate_filters(request)
    raw_text = request.get("raw_import_text")
    if raw_text is not None:
        if not isinstance(raw_text, str) or len(raw_text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("raw import exceeds byte limit")
        # Validate that the raw evidence is actually GeoJSON, without rewriting it.
        raw_geometry = geometry_document(strict_json(raw_text.encode("utf-8")))
        raw_import = {"text": raw_text, "sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
                      "format": "GeoJSON", "edited": raw_geometry != canonical}
    else:
        raw_import = None
    source_entries = registry.get("providers") if isinstance(registry, dict) else None
    if not isinstance(source_entries, dict):
        source_entries = {}
    rows, catalogs, unresolved = [], [], []
    if not source_entries:
        unresolved.append("PROVIDER_REGISTRY_EMPTY_OR_UNAVAILABLE")
    bbox = box(*processing.bounds)
    for dataset_id, provider in sorted(source_entries.items()):
        catalog = {"dataset_id": dataset_id, "state": "BLOCKED", "sha256": None,
                   "records": 0, "scope": "configured_snapshot_only", "reason": None}
        catalogs.append(catalog)
        try:
            if not isinstance(provider, dict):
                raise ValueError("INVALID_PROVIDER_CONFIG")
            raw, doc = safe_snapshot(root, provider)
        except (OSError, ValueError, TypeError) as exc:
            catalog["reason"] = str(exc)
            unresolved.append(f"{dataset_id}: {exc}")
            continue
        snapshot_hash = hashlib.sha256(raw).hexdigest()
        catalog.update(state="PASS", sha256=snapshot_hash, records=len(doc["features"]))
        for index, feature in enumerate(doc["features"]):
            props = feature.get("properties") if isinstance(feature, dict) else None
            props = props if isinstance(props, dict) else {}
            source = provider.get("provider_id", "UNRESOLVED")
            asset_id = props.get("asset_id")
            url = props.get("source_url")
            identity = [source, dataset_id, provider.get("catalog_version", snapshot_hash), asset_id]
            identity_bound = (all(isinstance(v, str) and v and v != "UNRESOLVED" for v in identity)
                              and isinstance(url, str) and bool(url))
            if identity_bound:
                try:
                    parsed_url = urlsplit(url)
                    identity_bound = (parsed_url.scheme == "https" and bool(parsed_url.hostname)
                                      and not parsed_url.username and not parsed_url.password)
                except ValueError:
                    identity_bound = False
            size = props.get("size_bytes")
            row = {
                "row_id": f"{dataset_id}:{index}", "asset_id": asset_id if isinstance(asset_id, str) and asset_id else "UNRESOLVED",
                "source": source if isinstance(source, str) and source else "UNRESOLVED",
                "dataset_id": dataset_id, "product": props.get("product", provider.get("dataset_class", "UNRESOLVED")),
                "acquisition_date": props.get("acquisition_date"), "resolution_m": props.get("resolution_m", provider.get("native_resolution_m")),
                "size_bytes": size if type(size) is int and size >= 0 else None,
                "source_url": url if isinstance(url, str) else None,
                "asset_key": digest(identity) if identity_bound else None,
                "raw_record": feature, "source_footprint": None, "aoi_intersection": None,
                "processing_intersection": None, "relation": "UNRESOLVED", "processing_relation": "UNRESOLVED",
                "bbox_candidate": False, "disposition": "UNRESOLVED", "required": False,
                "source_status": "SOURCE_BOUND" if identity_bound else "UNRESOLVED",
                "cache_state": "NOT_CHECKED", "acquisition_state": "UNRESOLVED",
                "validation_state": "NOT_RUN", "reasons": [],
            }
            rows.append(row)
            if not isinstance(row["product"], str) or not row["product"]:
                row["product"] = "UNRESOLVED"
                identity_bound = False
                row["source_status"] = "UNRESOLVED"
            footprint_doc = feature.get("geometry") if isinstance(feature, dict) else None
            if footprint_doc is None:
                row["relation"] = row["processing_relation"] = "NULL_EMPTY"
                row["reasons"].append("NULL_SOURCE_GEOMETRY")
                continue
            try:
                footprint_json, footprint, _ = valid_polygon(feature)
                row["source_footprint"] = footprint_json
                row["bbox_candidate"] = bbox.intersects(footprint)
                row["relation"], row["aoi_intersection"] = relation(aoi, footprint)
                row["processing_relation"], row["processing_intersection"] = relation(processing, footprint)
            except (ValueError, TypeError) as exc:
                row["reasons"].append(f"INVALID_SOURCE_GEOMETRY: {exc}")
                continue
            if row["processing_relation"] in ("OUTSIDE", "TOUCH_ONLY"):
                row["disposition"] = "EXCLUDED"
                row["reasons"].append(row["processing_relation"])
                continue
            disposition, reasons = filter_result(row, filters)
            row["disposition"] = disposition
            row["reasons"].extend(reasons)
            if disposition == "EXCLUDED":
                continue
            row["required"] = True
            if not identity_bound:
                row["disposition"] = "UNRESOLVED"
                row["reasons"].append("SOURCE_IDENTITY_OR_URL_UNBOUND")
    if len(rows) > MAX_ROWS:
        raise ValueError("combined catalog row limit exceeded")
    # Never turn repeated identities/URLs into silent deduplication or extra votes.
    keys = Counter(row["asset_key"] for row in rows if row["asset_key"])
    urls = Counter(row["source_url"] for row in rows if row["source_url"])
    for row in rows:
        duplicate = ((row["asset_key"] and keys[row["asset_key"]] > 1)
                     or (row["source_url"] and urls[row["source_url"]] > 1))
        if duplicate and row["required"]:
            row["disposition"] = "UNRESOLVED"
            row["reasons"].append("DUPLICATE_IDENTITY_OR_URL_REQUIRES_ADJUDICATION")
        if row["required"] and row["disposition"] == "RETAINED":
            # Pending cache inspection: all are transfer candidates, never cache hits.
            row["acquisition_state"] = "QUEUED"
    counts = {
        "discovered": len(rows),
        "retained": sum(r["disposition"] == "RETAINED" for r in rows),
        "excluded": sum(r["disposition"] == "EXCLUDED" for r in rows),
        "unresolved": sum(r["disposition"] == "UNRESOLVED" for r in rows),
        "required": sum(r["required"] for r in rows),
        "cache_valid": 0,
        "fetch_required": sum(r["required"] and r["disposition"] == "RETAINED" for r in rows),
        "blocked_required": sum(r["required"] and r["disposition"] == "UNRESOLVED" for r in rows),
    }
    if counts["unresolved"]:
        unresolved.append("CANDIDATE_RESIDUE: inspect every UNRESOLVED row")
    if counts["required"] == 0:
        unresolved.append("NO_REQUIRED_ASSETS: not an acquisition-ready plan")
    audit = (counts["discovered"] == counts["retained"] + counts["excluded"] + counts["unresolved"]
             and counts["required"] == counts["cache_valid"] + counts["fetch_required"] + counts["blocked_required"])
    if not audit:
        unresolved.append("ARITHMETIC_MISMATCH")
    ready = not unresolved and audit
    plan = {
        "schema_version": "aoi_acquisition_plan.v1.1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "PLAN_READY" if ready else "BLOCKED", "planning_gate": "PASS" if ready else "BLOCKED",
        "certification": "OPEN", "capabilities": {"fetch": False},
        "execution_blockers": ["ACQUISITION_CACHE_HASH_VALIDATION_NOT_CONNECTED"],
        "diagnostics": {"geometry_type": canonical["type"], "crs": "OGC:CRS84", "vertex_count": vertex_count,
                        "area_km2": area_km2(aoi), "valid": True, "messages": []},
        "input_kind": request.get("input_kind", "USER_GEOMETRY"), "raw_import": raw_import,
        "normalized_aoi": canonical, "processing_geometry": mapping(processing),
        "buffer_method": buffer_method, "discovery_bbox": list(processing.bounds),
        "aoi_sha256": digest(canonical), "filters": filters,
        "provider_registry_sha256": digest(registry), "catalogs": catalogs,
        "counts": counts, "assets": rows, "arithmetic_closed": audit,
        "estimated_download_bytes_known": sum(r["size_bytes"] or 0 for r in rows if r["required"]),
        "unknown_size_assets": sum(r["size_bytes"] is None for r in rows if r["required"]),
        "coverage": None, "coverage_state": "UNKNOWN", "unresolved_reasons": unresolved,
        "software": {"planner": "aoi-dry-run/1.1", "hash_convention": "sorted-keys-ascii-json-excluding-plan_id-and-plan_sha256"},
    }
    # Hash the entire returned evidence payload, not a subset of summary counters.
    plan["plan_sha256"] = digest(plan)
    plan["plan_id"] = f"aoi-{plan['plan_sha256']}"
    return plan
