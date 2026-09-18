#!/usr/bin/env python3
"""Compatibility-only monolithic SSURGO continuation.

The canonical Spiderweb SSURGO path is the modular LOCATION_QUERY chain:
location_query -> location_query_fetch -> ssurgo_location_stage2 ->
location_query_fetch -> ssurgo_location_stage3 -> location_query_fetch ->
certify_ssurgo_child.

This script is retained for backward compatibility only. It reimplements network
and cardinality logic, so it is NONCANONICAL and cannot certify the canonical
pipeline. Execution requires an explicit --allow-noncanonical-compat flag.
Raw WFS bytes remain preserved before any derived normalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from spiderweb.location_query_sources import query_bbox

SDA_ENDPOINT = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
USER_AGENT = "spiderweb-pr-location-query-ssurgo/1.0"
PARENT_BATCH_SIZE = 500


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_sha256(value: object) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit("FAIL: " + message)


def require_geo():
    try:
        import geopandas as gpd
        from pyproj import CRS, Transformer
        from shapely.geometry import Point, box, shape
        from shapely.ops import transform
    except ImportError as exc:
        raise SystemExit(
            "FAIL: SSURGO continuation requires the Spiderweb geo extra: pip install -e '.[geo]'"
        ) from exc
    return gpd, CRS, Transformer, Point, box, shape, transform


def _metric_epsg(lon: float, lat: float) -> int:
    zone = min(60, max(1, int(math.floor((lon + 180.0) / 6.0)) + 1))
    return (32600 if lat >= 0 else 32700) + zone


def aoi_geometry(query: dict[str, Any]):
    _, _, Transformer, Point, box, shape, transform = require_geo()
    g = query["geometry"]
    kind = g["type"]
    if kind == "bbox":
        return box(float(g["west"]), float(g["south"]), float(g["east"]), float(g["north"]))
    if kind == "point":
        return Point(float(g["lon"]), float(g["lat"]))
    if kind == "radius":
        lon, lat, radius = float(g["lon"]), float(g["lat"]), float(g["radius_m"])
        epsg = _metric_epsg(lon, lat)
        forward = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        reverse = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
        metric_point = transform(forward.transform, Point(lon, lat))
        return transform(reverse.transform, metric_point.buffer(radius))
    gj = g["geojson"]
    if gj.get("type") == "Feature":
        gj = gj.get("geometry") or {}
    elif gj.get("type") == "FeatureCollection":
        features = gj.get("features") or []
        geoms = [shape(feature["geometry"]) for feature in features if feature.get("geometry")]
        if not geoms:
            fail("GeoJSON FeatureCollection contains no geometries")
        from shapely.ops import unary_union
        return unary_union(geoms)
    return shape(gj)


def _bounds_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    aw, a_s, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and a_s <= bn and an >= bs


def normalize_wfs_gml(raw_path: Path, aoi_bbox: tuple[float, float, float, float]):
    gpd, _, _, _, _, _, transform = require_geo()
    frame = gpd.read_file(raw_path)
    if "geometry" not in frame.columns:
        fail(f"{raw_path}: geometry column missing")
    if frame.geometry.isna().any():
        fail(f"{raw_path}: null geometry")
    if frame.geometry.is_empty.any():
        fail(f"{raw_path}: empty geometry")
    if (~frame.geometry.is_valid).any():
        fail(f"{raw_path}: invalid geometry")

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

    raw_text = raw_path.read_bytes()[:262144]
    epsg4326_token = b"EPSG:4326" in raw_text or b"urn:ogc:def:crs:EPSG::4326" in raw_text

    if lonlat_hits and not latlon_hits:
        axis_state = "SOURCE_SERIALIZED_LONGITUDE_LATITUDE"
        fixed = frame.copy()
    elif latlon_hits and not lonlat_hits:
        axis_state = "SOURCE_SERIALIZED_LATITUDE_LONGITUDE"
        fixed = frame.copy()
        fixed.geometry = fixed.geometry.apply(
            lambda geom: transform(lambda x, y, z=None: (y, x) if z is None else (y, x, z), geom)
        )
    else:
        fail(
            f"{raw_path}: axis order unresolved; raw_bounds={raw_bounds} "
            f"lonlat_hits={lonlat_hits} latlon_hits={latlon_hits}"
        )

    fixed = fixed.set_crs("EPSG:4326", allow_override=True)
    return frame, fixed, {
        "raw_parsed_crs": str(frame.crs) if frame.crs is not None else None,
        "raw_bounds": list(raw_bounds),
        "source_epsg4326_token": epsg4326_token,
        "axis_state": axis_state,
        "normalized_bounds": [float(v) for v in fixed.total_bounds],
        "row_count": len(fixed),
    }


def _metric_geometry(geom):
    _, _, Transformer, _, _, _, transform = require_geo()
    centroid = geom.centroid
    epsg = _metric_epsg(float(centroid.x), float(centroid.y))
    forward = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return transform(forward.transform, geom), epsg


def _find_request(fetch: dict, provider_id: str, role: str) -> dict:
    rows = [
        row
        for row in fetch.get("requests", [])
        if row.get("provider_id") == provider_id and row.get("request_role") == role
    ]
    if len(rows) != 1:
        fail(f"expected exactly one {provider_id}/{role} fetch receipt; got {len(rows)}")
    return rows[0]


def _find_plan_request(plan: dict, provider_id: str, role: str) -> dict:
    rows = [
        row
        for row in plan.get("requests", [])
        if row.get("provider_id") == provider_id and row.get("request_role") == role
    ]
    if len(rows) != 1:
        fail(f"expected exactly one {provider_id}/{role} plan request; got {len(rows)}")
    return rows[0]


def _digits(values: list[str], label: str) -> list[str]:
    cleaned = [str(value).strip() for value in values]
    if any(not value or not value.isdigit() for value in cleaned):
        fail(f"{label}: non-numeric/null key")
    return cleaned


def _post_sda(sql: str, timeout: int) -> bytes:
    body = json.dumps(
        {"query": sql, "format": "JSON+COLUMNNAME"},
        separators=(",", ":"),
    ).encode("utf-8")
    req = Request(
        SDA_ENDPOINT,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            payload = response.read()
            status = getattr(response, "status", 200)
    except HTTPError as exc:
        payload = exc.read()
        raise SystemExit(
            f"FAIL: SDA HTTP {exc.code}: {payload[:1000].decode('utf-8', errors='replace')}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise SystemExit(f"FAIL: SDA request failed: {type(exc).__name__}: {exc}") from exc
    if status != 200 or not payload:
        fail(f"SDA status={status} empty={not bool(payload)}")
    return payload


def fetch_table(
    *,
    table: str,
    parent_key: str,
    parent_values: list[str],
    stable_key: str,
    output_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    parent_values = _digits(parent_values, f"{table}.{parent_key} denominator")
    if not parent_values:
        return {
            "table": table,
            "parent_key": parent_key,
            "stable_key": stable_key,
            "parent_denominator_count": 0,
            "row_count": 0,
            "unique_stable_keys": 0,
            "returned_parent_count": 0,
            "zero_child_parent_count": 0,
            "state": "NO_PARENT_ROWS",
            "batches": [],
            "header": [],
            "rows": [],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    header: list[str] | None = None
    rows: list[list[Any]] = []
    batches: list[dict[str, Any]] = []

    for batch_index, start in enumerate(range(0, len(parent_values), PARENT_BATCH_SIZE), 1):
        batch = parent_values[start : start + PARENT_BATCH_SIZE]
        in_clause = ", ".join(f"'{value}'" for value in batch)
        sql = (
            f"SELECT * FROM {table} "
            f"WHERE {parent_key} IN ({in_clause}) "
            f"ORDER BY {parent_key}, {stable_key}"
        )
        query_path = output_dir / f"{table}.batch_{batch_index:04d}.sql"
        query_path.write_text(sql + "\n", encoding="utf-8")
        payload = _post_sda(sql, timeout)
        raw_path = output_dir / f"{table}.batch_{batch_index:04d}.json"
        raw_path.write_bytes(payload)

        try:
            obj = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            fail(f"{table} batch {batch_index}: invalid JSON: {exc}")
        table_payload = obj.get("Table") if isinstance(obj, dict) else None
        if not isinstance(table_payload, list) or not table_payload:
            fail(f"{table} batch {batch_index}: response lacks Table")
        batch_header = table_payload[0]
        batch_rows = table_payload[1:]
        if not isinstance(batch_header, list) or any(not isinstance(value, str) for value in batch_header):
            fail(f"{table} batch {batch_index}: malformed header")
        if header is None:
            header = list(batch_header)
        elif header != batch_header:
            fail(f"{table}: runtime schema drift between batches")

        for row in batch_rows:
            if not isinstance(row, list) or len(row) != len(header):
                fail(f"{table} batch {batch_index}: row-width mismatch")
        rows.extend(batch_rows)
        batches.append({
            "batch_index": batch_index,
            "parent_key_count": len(batch),
            "query_path": str(query_path),
            "query_sha256": sha256_file(query_path),
            "raw_path": str(raw_path),
            "raw_sha256": sha256_bytes(payload),
            "row_count": len(batch_rows),
        })

    assert header is not None
    if parent_key not in header:
        fail(f"{table}: parent key {parent_key} absent from runtime schema")
    if stable_key not in header:
        fail(f"{table}: stable key {stable_key} absent from runtime schema")

    parent_index = header.index(parent_key)
    stable_index = header.index(stable_key)
    returned_parents: list[str] = []
    stable_keys: list[str] = []
    for row_number, row in enumerate(rows, 1):
        parent = "" if row[parent_index] is None else str(row[parent_index]).strip()
        stable = "" if row[stable_index] is None else str(row[stable_index]).strip()
        if not parent:
            fail(f"{table}: null parent key at logical row {row_number}")
        if not stable:
            fail(f"{table}: null stable key at logical row {row_number}")
        returned_parents.append(parent)
        stable_keys.append(stable)

    expected_parent_set = set(parent_values)
    returned_parent_set = set(returned_parents)
    foreign = sorted(returned_parent_set - expected_parent_set)
    if foreign:
        fail(f"{table}: foreign parent keys: {foreign[:20]}")
    if len(stable_keys) != len(set(stable_keys)):
        fail(f"{table}: duplicate stable keys")

    counts = {value: 0 for value in parent_values}
    for value in returned_parents:
        counts[value] += 1
    zero_parents = sorted(value for value, count in counts.items() if count == 0)
    one_parents = sorted(value for value, count in counts.items() if count == 1)
    multi_parents = sorted(value for value, count in counts.items() if count > 1)
    if sum(counts.values()) != len(rows):
        fail(f"{table}: parent-child arithmetic closure failed")

    return {
        "table": table,
        "parent_key": parent_key,
        "stable_key": stable_key,
        "parent_denominator_count": len(parent_values),
        "row_count": len(rows),
        "unique_stable_keys": len(set(stable_keys)),
        "returned_parent_count": len(returned_parent_set),
        "foreign_parent_count": 0,
        "zero_child_parent_count": len(zero_parents),
        "one_child_parent_count": len(one_parents),
        "multi_child_parent_count": len(multi_parents),
        "zero_child_parent_keys": zero_parents,
        "state": "PASS",
        "header": header,
        "rows": rows,
        "batches": batches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("fetch_receipt", type=Path)
    parser.add_argument("--children", type=Path, default=Path("configs/ssurgo_component_children.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--allow-noncanonical-compat",
        action="store_true",
        help="explicitly run the retained monolithic compatibility workflow",
    )
    args = parser.parse_args()
    if not args.allow_noncanonical_compat:
        fail(
            "location_query_ssurgo.py is NONCANONICAL compatibility only; "
            "use the modular SSURGO chain or pass --allow-noncanonical-compat explicitly"
        )

    if (args.output_dir / "SSURGO_LOCATION_QUERY_RECEIPT.json").exists():
        fail("output snapshot already exists; use a new versioned output directory")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    fetch = json.loads(args.fetch_receipt.read_text(encoding="utf-8"))
    query = plan.get("query")
    if not isinstance(query, dict):
        fail("plan.query missing")
    expected_plan_sha = canonical_json_sha256(plan)
    if fetch.get("plan_sha256") != expected_plan_sha:
        fail("fetch receipt plan SHA256 does not match acquisition plan")
    allow_partial = bool(query.get("allow_partial", False))
    aoi = aoi_geometry(query)
    aoi_bbox = tuple(float(v) for v in query_bbox(query))

    survey_receipt = _find_request(fetch, "SSURGO_SOILS", "SurveyAreaPoly")
    mapunit_receipt = _find_request(fetch, "SSURGO_SOILS", "MapunitPoly")
    survey_spec = _find_plan_request(plan, "SSURGO_SOILS", "SurveyAreaPoly")
    mapunit_spec = _find_plan_request(plan, "SSURGO_SOILS", "MapunitPoly")
    if survey_receipt.get("request_spec_sha256") != canonical_json_sha256(survey_spec):
        fail("SurveyAreaPoly receipt request-spec SHA256 mismatch")
    if mapunit_receipt.get("request_spec_sha256") != canonical_json_sha256(mapunit_spec):
        fail("MapunitPoly receipt request-spec SHA256 mismatch")
    if survey_receipt.get("state") == "NO_COVERAGE" or mapunit_receipt.get("state") == "NO_COVERAGE":
        result = {
            "schema_version": "spiderweb.location_query_ssurgo.v1.1",
            "classification": "NONCANONICAL_COMPATIBILITY",
            "state": "NO_COVERAGE",
            "query_id": query.get("query_id"),
            "raw_spatial_receipts": [survey_receipt, mapunit_receipt],
        }
        write_json(args.output_dir / "SSURGO_LOCATION_QUERY_RECEIPT.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if survey_receipt.get("state") != "PASS" or mapunit_receipt.get("state") != "PASS":
        fail("SSURGO spatial requests did not both PASS")

    survey_raw = Path(str(survey_receipt.get("raw_path")))
    mapunit_raw = Path(str(mapunit_receipt.get("raw_path")))
    if not survey_raw.is_file() or not mapunit_raw.is_file():
        fail("SSURGO raw GML source manifestation missing")
    if survey_receipt.get("sha256") != sha256_file(survey_raw):
        fail("SurveyAreaPoly raw SHA256 does not match fetch receipt")
    if mapunit_receipt.get("sha256") != sha256_file(mapunit_raw):
        fail("MapunitPoly raw SHA256 does not match fetch receipt")

    survey_source, survey, survey_axis = normalize_wfs_gml(survey_raw, aoi_bbox)
    mapunit_source, mapunits, mapunit_axis = normalize_wfs_gml(mapunit_raw, aoi_bbox)

    derived_dir = args.output_dir / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    survey_gpkg = derived_dir / "SurveyAreaPoly_EPSG4326.gpkg"
    mapunit_gpkg = derived_dir / "MapunitPoly_EPSG4326.gpkg"
    survey.to_file(survey_gpkg, driver="GPKG")
    mapunits.to_file(mapunit_gpkg, driver="GPKG")

    metric_aoi, metric_epsg = _metric_geometry(aoi)
    survey_metric = survey.to_crs(epsg=metric_epsg)
    survey_union = survey_metric.geometry.union_all()
    if metric_aoi.area > 0:
        gap_area = metric_aoi.difference(survey_union).area
        coverage_fraction = metric_aoi.intersection(survey_union).area / metric_aoi.area
        tolerance = max(1.0, metric_aoi.area * 1e-8)
        complete_coverage = gap_area <= tolerance
    else:
        gap_area = 0.0
        coverage_fraction = 1.0 if survey_union.covers(metric_aoi) else 0.0
        complete_coverage = bool(survey_union.covers(metric_aoi))

    if not complete_coverage and not allow_partial:
        fail(
            f"SSURGO survey-area coverage incomplete fraction={coverage_fraction} "
            f"gap_m2={gap_area}; set allow_partial=true for explicit partial workflows"
        )

    mapunit_metric = mapunits.to_crs(epsg=metric_epsg)
    retained_indices: list[int] = []
    touch_indices: list[int] = []
    intersection_areas: dict[int, float] = {}
    for index, geom in mapunit_metric.geometry.items():
        if not geom.intersects(metric_aoi):
            continue
        if metric_aoi.area == 0:
            retained_indices.append(index)
            intersection_areas[index] = 0.0
        else:
            area = geom.intersection(metric_aoi).area
            if area > 0:
                retained_indices.append(index)
                intersection_areas[index] = float(area)
            else:
                touch_indices.append(index)

    retained = mapunits.loc[retained_indices].copy()
    if "mukey" not in retained.columns:
        fail("MapunitPoly runtime schema lacks mukey")
    mukeys = _digits(retained["mukey"].astype(str).tolist(), "AOI MUKEY")
    unique_mukeys = sorted(set(mukeys), key=lambda value: (len(value), value))
    if not unique_mukeys:
        fail("AOI intersects zero positive MapunitPoly MUKEYs")
    if "mupolygonkey" in retained.columns:
        polygon_keys = [str(value).strip() for value in retained["mupolygonkey"].tolist()]
        if any(not value for value in polygon_keys) or len(polygon_keys) != len(set(polygon_keys)):
            fail("retained MapunitPoly mupolygonkey null/duplicate")

    retained_gpkg = derived_dir / "MapunitPoly_AOI_RETAINED.gpkg"
    retained.to_file(retained_gpkg, driver="GPKG")
    spatial_denominator = {
        "classification": "SSURGO_MAPUNITPOLY_LOCATION_QUERY_MUKEY_DENOMINATOR",
        "state": "PASS",
        "query_id": query.get("query_id"),
        "metric_epsg": metric_epsg,
        "coverage_fraction": coverage_fraction,
        "gap_area_m2": gap_area,
        "survey_complete": complete_coverage,
        "survey_source_rows": len(survey_source),
        "mapunit_source_rows": len(mapunit_source),
        "retained_polygon_rows": len(retained),
        "touch_only_rows": len(touch_indices),
        "unique_mukey_count": len(unique_mukeys),
        "mukeys": unique_mukeys,
        "survey_axis_adjudication": survey_axis,
        "mapunit_axis_adjudication": mapunit_axis,
        "raw_sources": {
            "SurveyAreaPoly": {"path": str(survey_raw), "sha256": sha256_file(survey_raw)},
            "MapunitPoly": {"path": str(mapunit_raw), "sha256": sha256_file(mapunit_raw)},
        },
        "derived": {
            "survey_gpkg": {"path": str(survey_gpkg), "sha256": sha256_file(survey_gpkg)},
            "mapunit_gpkg": {"path": str(mapunit_gpkg), "sha256": sha256_file(mapunit_gpkg)},
            "retained_gpkg": {"path": str(retained_gpkg), "sha256": sha256_file(retained_gpkg)},
        },
    }
    write_json(args.output_dir / "SSURGO_MUKEY_DENOMINATOR.json", spatial_denominator)

    tabular_dir = args.output_dir / "raw_tabular"
    mapunit = fetch_table(
        table="mapunit",
        parent_key="mukey",
        parent_values=unique_mukeys,
        stable_key="mukey",
        output_dir=tabular_dir,
        timeout=args.timeout,
    )
    mapunit_returned = sorted(
        {str(row[mapunit["header"].index("mukey")]).strip() for row in mapunit["rows"]},
        key=lambda value: (len(value), value),
    )
    if mapunit_returned != unique_mukeys:
        fail("mapunit returned MUKEY set != certified AOI MUKEY denominator")

    component = fetch_table(
        table="component",
        parent_key="mukey",
        parent_values=unique_mukeys,
        stable_key="cokey",
        output_dir=tabular_dir,
        timeout=args.timeout,
    )
    cokey_index = component["header"].index("cokey")
    cokeys = _digits(
        [str(row[cokey_index]) for row in component["rows"]],
        "component COKEY",
    )
    unique_cokeys = sorted(set(cokeys), key=lambda value: (len(value), value))
    if len(unique_cokeys) != len(cokeys):
        fail("component COKEY duplicates")

    child_cfg = json.loads(args.children.read_text(encoding="utf-8"))
    child_rows = child_cfg.get("records")
    if not isinstance(child_rows, list) or child_cfg.get("relationship_count") != len(child_rows):
        fail("SSURGO child-table config denominator drift")
    child_names = [str(row.get("table", "")).strip() for row in child_rows]
    if len(child_names) != len(set(child_names)):
        fail("SSURGO child-table config duplicate tables")

    children: list[dict[str, Any]] = []
    for child in child_rows:
        table = str(child["table"])
        stable_key = str(child["stable_key"])
        result = fetch_table(
            table=table,
            parent_key="cokey",
            parent_values=unique_cokeys,
            stable_key=stable_key,
            output_dir=tabular_dir,
            timeout=args.timeout,
        )
        result["key_evidence"] = child.get("key_evidence")
        result["constraint_name_state"] = child.get("constraint_name_state")
        children.append(result)

    total_child_rows = sum(row["row_count"] for row in children)
    if len(children) != child_cfg["relationship_count"]:
        fail("child-table execution denominator did not close")

    result = {
        "schema_version": "spiderweb.location_query_ssurgo.v1.1",
        "classification": "NONCANONICAL_COMPATIBILITY",
        "canonical_certification": False,
        "state": "PASS" if complete_coverage else "PARTIAL",
        "query_id": query.get("query_id"),
        "allow_partial": allow_partial,
        "spatial_denominator": spatial_denominator,
        "mapunit": {
            key: value
            for key, value in mapunit.items()
            if key != "rows"
        },
        "component": {
            key: value
            for key, value in component.items()
            if key != "rows"
        },
        "cokey_denominator": {
            "count": len(unique_cokeys),
            "cokeys": unique_cokeys,
        },
        "child_table_denominator": {
            "documentation_epoch": child_cfg.get("current_documentation_epoch"),
            "count": len(children),
            "prior_frozen_count": (child_cfg.get("lineage") or {}).get("prior_frozen_relationship_count"),
            "total_child_rows": total_child_rows,
            "records": [
                {
                    key: value
                    for key, value in child.items()
                    if key not in {"rows", "header"}
                }
                for child in children
            ],
        },
        "invariants": {
            "mukey_set_equal": mapunit_returned == unique_mukeys,
            "component_cokey_unique": len(cokeys) == len(unique_cokeys),
            "child_table_count_closed": len(children) == child_cfg["relationship_count"],
            "child_parent_foreign_zero": all(row.get("foreign_parent_count", 0) == 0 for row in children),
            "child_stable_keys_unique": all(row.get("row_count") == row.get("unique_stable_keys") for row in children),
            "one_to_n_flattening": False,
            "raw_bytes_preserved_before_derivation": True,
        },
        "next_gate": (
            "REPLAY_WITH_CANONICAL_MODULAR_SSURGO_CHAIN"
            if complete_coverage
            else "PARTIAL_NONCANONICAL_COMPATIBILITY_RESULT"
        ),
    }
    receipt = args.output_dir / "SSURGO_LOCATION_QUERY_RECEIPT.json"
    write_json(receipt, result)
    print(json.dumps({
        "state": result["state"],
        "mukeys": len(unique_mukeys),
        "cokeys": len(unique_cokeys),
        "child_tables": len(children),
        "child_rows": total_child_rows,
        "receipt": str(receipt),
        "receipt_sha256": sha256_file(receipt),
    }, indent=2, sort_keys=True))
    return 0 if result["state"] in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
