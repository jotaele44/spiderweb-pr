"""Exact SSURGO spatial adjudication for canonical LOCATION_QUERY.

Raw WFS GML remains the source manifestation. This module only derives an
EPSG:4326-normalized interpretation after adjudicating source axis order against
the query envelope, then certifies SurveyArea coverage and the exact
MapunitPoly->MUKEY denominator for the original point/radius/bbox/GeoJSON AOI.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from spiderweb.location_query_sources import query_bbox


class SSURGOSpatialError(ValueError):
    """Fail-closed SSURGO spatial adjudication error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_key_sha256(values: list[str]) -> str:
    return sha256_bytes(("\n".join(values) + "\n").encode("utf-8"))


def _require_geo():
    try:
        import geopandas as gpd
        from pyproj import Transformer
        from shapely.geometry import Point, box, shape
        from shapely.ops import transform, unary_union
    except ImportError as exc:
        raise SSURGOSpatialError(
            "SSURGO exact spatial adjudication requires the geo extra"
        ) from exc
    return gpd, Transformer, Point, box, shape, transform, unary_union


def _metric_epsg(lon: float, lat: float) -> int:
    zone = min(60, max(1, int(math.floor((lon + 180.0) / 6.0)) + 1))
    return (32600 if lat >= 0 else 32700) + zone


def _bounds_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    aw, a_s, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and a_s <= bn and an >= bs


def aoi_geometry(query: dict[str, Any]):
    _, Transformer, Point, box, shape, transform, unary_union = _require_geo()
    geometry = query.get("geometry")
    if not isinstance(geometry, dict):
        raise SSURGOSpatialError("query.geometry missing")
    kind = geometry.get("type")
    if kind == "bbox":
        return box(
            float(geometry["west"]),
            float(geometry["south"]),
            float(geometry["east"]),
            float(geometry["north"]),
        )
    if kind == "point":
        return Point(float(geometry["lon"]), float(geometry["lat"]))
    if kind == "radius":
        lon = float(geometry["lon"])
        lat = float(geometry["lat"])
        radius = float(geometry["radius_m"])
        if radius <= 0:
            raise SSURGOSpatialError("radius_m must be positive")
        epsg = _metric_epsg(lon, lat)
        forward = Transformer.from_crs(
            "EPSG:4326", f"EPSG:{epsg}", always_xy=True
        )
        reverse = Transformer.from_crs(
            f"EPSG:{epsg}", "EPSG:4326", always_xy=True
        )
        metric_point = transform(forward.transform, Point(lon, lat))
        return transform(reverse.transform, metric_point.buffer(radius))

    if kind not in {"polygon", "geojson"}:
        raise SSURGOSpatialError(f"unsupported geometry type: {kind!r}")
    geojson = geometry.get("geojson")
    if not isinstance(geojson, dict):
        raise SSURGOSpatialError("geometry.geojson missing")
    value = geojson
    if value.get("type") == "Feature":
        value = value.get("geometry") or {}
    elif value.get("type") == "FeatureCollection":
        features = value.get("features") or []
        geometries = [
            shape(feature["geometry"])
            for feature in features
            if isinstance(feature, dict) and feature.get("geometry")
        ]
        if not geometries:
            raise SSURGOSpatialError(
                "GeoJSON FeatureCollection contains no geometries"
            )
        return unary_union(geometries)
    return shape(value)


def _metric_geometry(geometry):
    _, Transformer, _, _, _, transform, _ = _require_geo()
    centroid = geometry.centroid
    epsg = _metric_epsg(float(centroid.x), float(centroid.y))
    forward = Transformer.from_crs(
        "EPSG:4326", f"EPSG:{epsg}", always_xy=True
    )
    return transform(forward.transform, geometry), epsg


def _verify_source_receipt(
    *,
    raw_path: Path,
    receipt: dict[str, Any],
    request_role: str,
) -> str:
    if receipt.get("provider_id") != "SSURGO_SOILS":
        raise SSURGOSpatialError(
            f"{request_role}: receipt provider is not SSURGO_SOILS"
        )
    if receipt.get("request_role") != request_role:
        raise SSURGOSpatialError(
            f"{request_role}: receipt request_role mismatch"
        )
    if receipt.get("state") != "PASS":
        raise SSURGOSpatialError(
            f"{request_role}: source acquisition receipt is not PASS"
        )
    if not raw_path.is_file():
        raise SSURGOSpatialError(
            f"{request_role}: raw manifestation missing: {raw_path}"
        )
    actual = sha256_file(raw_path)
    if receipt.get("sha256") != actual:
        raise SSURGOSpatialError(
            f"{request_role}: raw SHA256 does not match receipt"
        )
    return actual


def normalize_wfs_gml(
    raw_path: Path,
    *,
    aoi_bbox: tuple[float, float, float, float],
):
    gpd, _, _, _, _, transform, _ = _require_geo()
    frame = gpd.read_file(raw_path)
    if "geometry" not in frame.columns:
        raise SSURGOSpatialError(f"{raw_path}: geometry column missing")
    if frame.empty:
        raise SSURGOSpatialError(f"{raw_path}: source contains zero rows")
    if frame.geometry.isna().any():
        raise SSURGOSpatialError(f"{raw_path}: null geometry")
    if frame.geometry.is_empty.any():
        raise SSURGOSpatialError(f"{raw_path}: empty geometry")
    if (~frame.geometry.is_valid).any():
        raise SSURGOSpatialError(f"{raw_path}: invalid source geometry")

    raw_bounds = tuple(float(value) for value in frame.total_bounds)
    lonlat_bounds = raw_bounds
    latlon_bounds = (
        raw_bounds[1],
        raw_bounds[0],
        raw_bounds[3],
        raw_bounds[2],
    )
    lonlat_hits = _bounds_intersect(lonlat_bounds, aoi_bbox)
    latlon_hits = _bounds_intersect(latlon_bounds, aoi_bbox)
    raw_prefix = raw_path.read_bytes()[:262144]
    epsg4326_token = (
        b"EPSG:4326" in raw_prefix
        or b"urn:ogc:def:crs:EPSG::4326" in raw_prefix
    )

    if lonlat_hits and not latlon_hits:
        axis_state = "SOURCE_SERIALIZED_LONGITUDE_LATITUDE"
        fixed = frame.copy()
    elif latlon_hits and not lonlat_hits:
        axis_state = "SOURCE_SERIALIZED_LATITUDE_LONGITUDE"
        fixed = frame.copy()
        fixed.geometry = fixed.geometry.apply(
            lambda geom: transform(
                lambda x, y, z=None: (
                    (y, x) if z is None else (y, x, z)
                ),
                geom,
            )
        )
    else:
        raise SSURGOSpatialError(
            f"{raw_path}: axis order unresolved; raw_bounds={raw_bounds} "
            f"lonlat_hits={lonlat_hits} latlon_hits={latlon_hits}"
        )

    fixed = fixed.set_crs("EPSG:4326", allow_override=True)
    return fixed, {
        "raw_parsed_crs": (
            str(frame.crs) if frame.crs is not None else None
        ),
        "raw_bounds": list(raw_bounds),
        "source_epsg4326_token": epsg4326_token,
        "axis_state": axis_state,
        "normalized_bounds": [float(v) for v in fixed.total_bounds],
        "row_count": len(fixed),
    }


def certify_exact_spatial_denominator(
    *,
    query: dict[str, Any],
    survey_raw_path: Path,
    survey_receipt: dict[str, Any],
    mapunit_raw_path: Path,
    mapunit_receipt: dict[str, Any],
) -> dict[str, Any]:
    allow_partial = bool(query.get("allow_partial", False))
    survey_sha = _verify_source_receipt(
        raw_path=survey_raw_path,
        receipt=survey_receipt,
        request_role="SurveyAreaPoly",
    )
    mapunit_sha = _verify_source_receipt(
        raw_path=mapunit_raw_path,
        receipt=mapunit_receipt,
        request_role="MapunitPoly",
    )

    aoi = aoi_geometry(query)
    if aoi.is_empty or not aoi.is_valid:
        raise SSURGOSpatialError("resolved AOI geometry is empty/invalid")
    aoi_bbox = tuple(float(value) for value in query_bbox(query))

    survey, survey_axis = normalize_wfs_gml(
        survey_raw_path,
        aoi_bbox=aoi_bbox,
    )
    mapunits, mapunit_axis = normalize_wfs_gml(
        mapunit_raw_path,
        aoi_bbox=aoi_bbox,
    )

    metric_aoi, metric_epsg = _metric_geometry(aoi)
    survey_metric = survey.to_crs(epsg=metric_epsg)
    _, _, _, _, _, _, unary_union = _require_geo()
    survey_union = unary_union(list(survey_metric.geometry))

    if metric_aoi.area > 0:
        aoi_area = float(metric_aoi.area)
        covered_area = float(metric_aoi.intersection(survey_union).area)
        gap_area = float(metric_aoi.difference(survey_union).area)
        coverage_fraction = covered_area / aoi_area
        tolerance = max(1.0, aoi_area * 1e-8)
        coverage_complete = gap_area <= tolerance
    else:
        aoi_area = 0.0
        coverage_complete = bool(survey_union.covers(metric_aoi))
        covered_area = 0.0
        gap_area = 0.0
        coverage_fraction = 1.0 if coverage_complete else 0.0
        tolerance = 0.0

    if not coverage_complete and not allow_partial:
        raise SSURGOSpatialError(
            "SurveyArea coverage incomplete for exact AOI: "
            f"coverage_fraction={coverage_fraction} gap_m2={gap_area}"
        )

    mapunit_metric = mapunits.to_crs(epsg=metric_epsg)
    retained_indices: list[Any] = []
    touch_only_indices: list[Any] = []
    intersection_area_m2: dict[str, float] = {}

    for index, geometry in mapunit_metric.geometry.items():
        if not geometry.intersects(metric_aoi):
            continue
        if metric_aoi.area == 0:
            retained_indices.append(index)
            intersection_area_m2[str(index)] = 0.0
            continue
        area = float(geometry.intersection(metric_aoi).area)
        if area > 0:
            retained_indices.append(index)
            intersection_area_m2[str(index)] = area
        else:
            touch_only_indices.append(index)

    retained = mapunits.loc[retained_indices].copy()
    if retained.empty:
        raise SSURGOSpatialError(
            "exact AOI intersects zero retained MapunitPoly rows"
        )
    if "mukey" not in retained.columns:
        raise SSURGOSpatialError("MapunitPoly runtime schema lacks mukey")

    raw_mukeys = [
        "" if value is None else str(value).strip()
        for value in retained["mukey"].tolist()
    ]
    if any(not value or not value.isdigit() for value in raw_mukeys):
        raise SSURGOSpatialError(
            "retained MapunitPoly contains null/non-numeric MUKEY"
        )
    mukeys = sorted(set(raw_mukeys), key=int)
    if not mukeys:
        raise SSURGOSpatialError("exact AOI MUKEY denominator is empty")

    polygon_key_state = "ABSENT"
    polygon_key_count = None
    if "mupolygonkey" in retained.columns:
        polygon_keys = [
            "" if value is None else str(value).strip()
            for value in retained["mupolygonkey"].tolist()
        ]
        if any(not value for value in polygon_keys):
            raise SSURGOSpatialError(
                "retained MapunitPoly contains null mupolygonkey"
            )
        if len(polygon_keys) != len(set(polygon_keys)):
            raise SSURGOSpatialError(
                "retained MapunitPoly contains duplicate mupolygonkey"
            )
        polygon_key_state = "UNIQUE_NON_NULL"
        polygon_key_count = len(polygon_keys)

    state = "PASS" if coverage_complete else "PARTIAL"
    return {
        "schema_version":
            "spiderweb.ssurgo_exact_spatial_denominator.v1.0",
        "state": state,
        "query_id": query.get("query_id"),
        "geometry_type": (query.get("geometry") or {}).get("type"),
        "allow_partial": allow_partial,
        "metric_epsg": metric_epsg,
        "aoi": {
            "bbox_wgs84": list(aoi_bbox),
            "area_m2": aoi_area,
        },
        "survey_coverage": {
            "complete": coverage_complete,
            "coverage_fraction": coverage_fraction,
            "covered_area_m2": covered_area,
            "gap_area_m2": gap_area,
            "gap_tolerance_m2": tolerance,
            "source_row_count": len(survey),
        },
        "selection": {
            "mapunit_source_row_count": len(mapunits),
            "retained_polygon_row_count": len(retained),
            "touch_only_row_count": len(touch_only_indices),
            "mukey_count": len(mukeys),
            "mukeys": mukeys,
            "canonical_mukey_set_sha256": canonical_key_sha256(mukeys),
            "mupolygonkey_state": polygon_key_state,
            "mupolygonkey_count": polygon_key_count,
            "intersection_area_m2_by_source_index":
                intersection_area_m2,
        },
        "source_manifestations": {
            "SurveyAreaPoly": {
                "path": str(survey_raw_path),
                "sha256": survey_sha,
                "axis_adjudication": survey_axis,
            },
            "MapunitPoly": {
                "path": str(mapunit_raw_path),
                "sha256": mapunit_sha,
                "axis_adjudication": mapunit_axis,
            },
        },
        "policy": {
            "raw_bytes_preserved": True,
            "geometry_normalization_is_derived": True,
            "axis_order_adjudicated_from_source_and_aoi": True,
            "positive_area_required_for_area_aoi": True,
            "touch_only_excluded_for_area_aoi": True,
            "point_aoi_uses_intersection": True,
            "survey_coverage_required_unless_allow_partial": True,
            "count_equality_used_as_identity": False,
        },
    }
