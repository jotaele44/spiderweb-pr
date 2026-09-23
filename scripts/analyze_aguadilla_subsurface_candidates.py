from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon, shape, mapping
from shapely.ops import transform as shp_transform, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/subsurface/aguadilla_maleza_alta_001"
RAW = OUT / "raw"
DERIVED = OUT / "derived"
DERIVED.mkdir(parents=True, exist_ok=True)

ANCHOR = (-67.1140566, 18.5091743)
WINDOWS = {
    "Z1": (-67.1614065, 18.4640016, -67.0667067, 18.5543470),
    "Z2": (-67.1235266, 18.5001398, -67.1045866, 18.5182088),
    "Z3": (-67.1164241, 18.5069157, -67.1116891, 18.5114329),
    "Z4": (-67.1145301, 18.5087226, -67.1135831, 18.5096260),
}

TO_UTM = Transformer.from_crs(4269, 32619, always_xy=True)
TO_WGS = Transformer.from_crs(4269, 4326, always_xy=True)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json_glob(prefix: str) -> dict:
    files = sorted(RAW.glob(prefix + ".*.raw"))
    if len(files) != 1:
        raise RuntimeError(f"{prefix}: expected exactly one frozen response, got {len(files)}")
    return json.loads(files[0].read_bytes())


def esri_polygon(geom: dict):
    rings = geom.get("rings") or []
    polys = []
    for ring in rings:
        if len(ring) >= 4:
            p = Polygon(ring)
            if not p.is_empty:
                if not p.is_valid:
                    p = p.buffer(0)
                if not p.is_empty:
                    polys.append(p)
    return unary_union(polys) if polys else None


def esri_lines(geom: dict):
    return [LineString(p) for p in (geom.get("paths") or []) if len(p) >= 2]


def freeze_json(name: str, obj: object) -> dict:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    digest = sha256_bytes(payload)
    path = DERIVED / f"{name}.{digest}.json"
    path.write_bytes(json.dumps(obj, indent=2, sort_keys=True).encode() + b"\n")
    return {"path": str(path.relative_to(ROOT)), "sha256": digest, "size_bytes": path.stat().st_size}


def raster_candidates() -> tuple[list[dict], dict]:
    tif_paths = sorted(RAW.glob("NOAA_CUDEM_PR_*.tif"))
    if len(tif_paths) != 2:
        raise RuntimeError(f"expected two CUDEM tiles, got {len(tif_paths)}")
    datasets = [rasterio.open(p) for p in tif_paths]
    candidates: list[dict] = []
    summary: dict = {}
    try:
        mosaic, transform = merge(datasets, bounds=WINDOWS["Z1"], nodata=datasets[0].nodata)
        band = mosaic[0].astype("float64")
        nodata = datasets[0].nodata
        if nodata is not None:
            band[band == nodata] = np.nan

        xres = abs(transform.a)
        yres = abs(transform.e)
        m_per_deg_lon = 111320.0 * math.cos(math.radians(ANCHOR[1]))
        m_per_deg_lat = 110574.0
        dx = max(xres * m_per_deg_lon, 0.1)
        dy = max(yres * m_per_deg_lat, 0.1)

        for zid, bbox in WINDOWS.items():
            w = from_bounds(*bbox, transform=transform)
            r0 = max(0, int(math.floor(w.row_off)))
            c0 = max(0, int(math.floor(w.col_off)))
            r1 = min(band.shape[0], int(math.ceil(w.row_off + w.height)))
            c1 = min(band.shape[1], int(math.ceil(w.col_off + w.width)))
            z = band[r0:r1, c0:c1]
            valid = np.isfinite(z)
            if z.shape[0] < 2 or z.shape[1] < 2 or valid.sum() < 4:
                summary[zid] = {"state": "UNRESOLVED", "reason": "insufficient raster cells"}
                continue
            fill = np.where(valid, z, np.nanmedian(z[valid]))
            lap = ndimage.laplace(fill)
            local_min = fill == ndimage.minimum_filter(fill, size=5, mode="nearest")
            local_max = ndimage.maximum_filter(fill, size=11, mode="nearest")
            prominence = local_max - fill
            depression = local_min & valid & (prominence >= 0.5)

            sink = np.ones(fill.shape, dtype=bool)
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    if oy == 0 and ox == 0:
                        continue
                    shifted = np.roll(np.roll(fill, oy, axis=0), ox, axis=1)
                    sink &= fill <= shifted
            sink &= valid

            curvature_threshold = float(np.nanpercentile(np.abs(lap[valid]), 99.5))
            lineament = valid & (np.abs(lap) >= curvature_threshold)

            window_transform = rasterio.windows.transform(
                rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0), transform
            )
            masks = {
                "DEPRESSION": depression,
                "FLOW_SINK_SCREEN": sink,
                "TERRAIN_LINEAMENT": lineament,
            }
            counts = {}
            for kind, mask in masks.items():
                feature_count = 0
                for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=window_transform, connectivity=8):
                    if int(value) != 1:
                        continue
                    g = shape(geom)
                    if g.is_empty:
                        continue
                    norm = g.normalize()
                    gsha = sha256_bytes(norm.wkb)
                    centroid = g.centroid
                    lon_wgs, lat_wgs = TO_WGS.transform(centroid.x, centroid.y)
                    rec = {
                        "candidate_id": f"{zid}-{kind}-{gsha[:20]}",
                        "zoom": zid,
                        "candidate_type": kind,
                        "state": "CANDIDATE",
                        "geometry_native": mapping(g),
                        "geometry_crs": "EPSG:4269 horizontal coordinates inherited from NOAA CUDEM",
                        "geometry_sha256": gsha,
                        "centroid_native": [centroid.x, centroid.y],
                        "centroid_wgs84": [lon_wgs, lat_wgs],
                        "area_native_degree2": g.area,
                        "identity_boundary": "one derived raster morphology observation; cross-zoom overlap/proximity is not canonical identity",
                    }
                    candidates.append(rec)
                    feature_count += 1
                counts[kind] = feature_count
            summary[zid] = {
                "state": "OBSERVED_DERIVED",
                "shape": [int(z.shape[0]), int(z.shape[1])],
                "valid_cells": int(valid.sum()),
                "component_counts": counts,
            }
    finally:
        for ds in datasets:
            ds.close()
    return candidates, summary


def build_context(candidates: list[dict]) -> dict:
    payloads = {
        sid: read_json_glob(sid)
        for sid in [
            "PRPB_SINKHOLES_4", "PRPB_CAVES_31", "PRPB_SPRINGS_19",
            "PRPB_WELLS_JCA_20", "PRPB_WELLS_AAA_21", "PRPB_RIVERS_23",
        ]
    }
    usgs = read_json_glob("USGS_MONITORING_LOCATIONS_PR")

    sink_geoms = []
    for f in payloads["PRPB_SINKHOLES_4"].get("features") or []:
        g = esri_polygon(f.get("geometry") or {})
        if g is not None:
            sink_geoms.append(g)
    sink_union = unary_union(sink_geoms) if sink_geoms else None

    river_geoms = []
    river_records = []
    for f in payloads["PRPB_RIVERS_23"].get("features") or []:
        attrs = f.get("attributes") or {}
        for g in esri_lines(f.get("geometry") or {}):
            river_geoms.append(g)
            river_records.append((g, attrs))
    river_union = unary_union(river_geoms) if river_geoms else None

    anchor = Point(*ANCHOR)
    anchor_utm = shp_transform(TO_UTM.transform, anchor)
    sink_dist = None
    sink_intersects = False
    if sink_union is not None:
        sink_intersects = anchor.intersects(sink_union)
        sink_dist = float(anchor_utm.distance(shp_transform(TO_UTM.transform, sink_union)))

    nearest_rivers = []
    for g, attrs in river_records:
        dist = float(anchor_utm.distance(shp_transform(TO_UTM.transform, g)))
        nearest_rivers.append({
            "distance_m": dist,
            "OBJECTID": attrs.get("OBJECTID"),
            "NAME_raw": attrs.get("NAME"),
            "Perennial_raw": attrs.get("Perennial"),
        })
    nearest_rivers.sort(key=lambda x: (x["distance_m"], x["OBJECTID"] if x["OBJECTID"] is not None else -1))

    ids = []
    usgs_sites = []
    for feature in usgs.get("features") or []:
        fid = feature.get("id")
        ids.append(fid)
        geom = feature.get("geometry")
        if not geom:
            continue
        p = shape(geom)
        props = feature.get("properties") or {}
        dist = float(anchor_utm.distance(shp_transform(TO_UTM.transform, p)))
        usgs_sites.append({
            "id": fid,
            "distance_m": dist,
            "coordinates": list(p.coords)[0],
            "name_raw": props.get("monitoring_location_name"),
            "site_type_raw": props.get("site_type"),
            "site_type_code_raw": props.get("site_type_code"),
        })
    usgs_sites.sort(key=lambda x: (x["distance_m"], x["id"] or ""))

    non_null = [x for x in ids if x is not None]
    source_counts = {sid: len(payload.get("features") or []) for sid, payload in payloads.items()}
    source_counts["USGS_MONITORING_LOCATIONS_PR"] = len(ids)

    for rec in candidates:
        p = Point(*rec["centroid_native"])
        pm = shp_transform(TO_UTM.transform, p)
        if sink_union is None:
            rec["mapped_sinkhole_relation"] = "SOURCE_EMPTY"
            rec["mapped_sinkhole_distance_m"] = None
        else:
            rec["mapped_sinkhole_relation"] = "INTERSECTS" if p.intersects(sink_union) else "OUTSIDE"
            rec["mapped_sinkhole_distance_m"] = float(pm.distance(shp_transform(TO_UTM.transform, sink_union)))
        if river_union is None:
            rec["mapped_river_relation"] = "SOURCE_EMPTY"
            rec["mapped_river_distance_m"] = None
        else:
            rec["mapped_river_relation"] = "INTERSECTS" if p.intersects(river_union) else "OUTSIDE"
            rec["mapped_river_distance_m"] = float(pm.distance(shp_transform(TO_UTM.transform, river_union)))
        rec["falsification_state"] = "OPEN"
        rec["falsifiers_required"] = [
            "ordinary_surface_drainage_or_topographic_concavity",
            "road_path_excavation_or_quarry",
            "vegetation_or_imagery_shadow",
            "DEM_tile_or_processing_seam",
            "coastal_surf_reef_or_wave_pattern_if_shoreward",
            "independent_subsurface_identity_evidence_absent",
        ]

    return {
        "source_counts": source_counts,
        "source_arithmetic": {
            sid: {"source": n, "retained": n, "excluded": 0, "unresolved": 0, "closed": True}
            for sid, n in source_counts.items()
        },
        "sinkholes": {
            "anchor_relation": "INTERSECTS" if sink_intersects else "OUTSIDE",
            "nearest_geometry_distance_m": sink_dist,
            "source_absence_boundary": "mapped geometry is not an exhaustive cave/void inventory",
        },
        "rivers": {"nearest_10": nearest_rivers[:10]},
        "caves": {"returned_features": source_counts["PRPB_CAVES_31"], "source_absence_boundary": "zero returned features does not prove no cave"},
        "springs": {"returned_features": source_counts["PRPB_SPRINGS_19"], "source_absence_boundary": "zero returned features does not prove no spring"},
        "wells_jca": {"returned_features": source_counts["PRPB_WELLS_JCA_20"]},
        "wells_aaa": {"returned_features": source_counts["PRPB_WELLS_AAA_21"]},
        "usgs_monitoring": {
            "rows": len(ids),
            "unique_ids": len(set(non_null)),
            "null_ids": sum(x is None for x in ids),
            "duplicate_ids": len(non_null) - len(set(non_null)),
            "nearest_22": usgs_sites[:22],
        },
    }


def main() -> int:
    candidates, zoom_summary = raster_candidates()
    context = build_context(candidates)

    candidate_ids = [x["candidate_id"] for x in candidates]
    duplicates = len(candidate_ids) - len(set(candidate_ids))
    null_ids = sum(x is None for x in candidate_ids)
    classification_counts = {}
    for rec in candidates:
        classification_counts[rec["state"]] = classification_counts.get(rec["state"], 0) + 1

    candidate_payload = {
        "schema": "spiderweb.subsurface.morphology_candidates.v1",
        "benchmark_id": "AGUADILLA_MALEZA_ALTA_SUBSURFACE_001",
        "source_definition": "complete connected-component set for the declared depression, flow-sink-screen and terrain-lineament masks at Z1-Z4",
        "cross_zoom_identity_rule": "separate observations retained; no proximity-only or overlap-only merges",
        "candidate_count": len(candidates),
        "candidate_id_duplicates": duplicates,
        "candidate_id_nulls": null_ids,
        "classification_counts": classification_counts,
        "zoom_summary": zoom_summary,
        "candidates": candidates,
    }
    context_payload = {
        "schema": "spiderweb.subsurface.authoritative_context.v1",
        "benchmark_id": "AGUADILLA_MALEZA_ALTA_SUBSURFACE_001",
        **context,
    }
    falsification_payload = {
        "schema": "spiderweb.subsurface.falsification_summary.v1",
        "benchmark_id": "AGUADILLA_MALEZA_ALTA_SUBSURFACE_001",
        "candidate_count": len(candidates),
        "open_falsification_count": sum(x["falsification_state"] == "OPEN" for x in candidates),
        "verified_subsurface_identity_count": 0,
        "certification_effect": "BLOCKED until every material candidate is independently adjudicated or excluded and temporal pixel persistence is closed",
        "prohibited_identity_promotions": [
            "DEPRESSION -> CAVE",
            "FLOW_SINK_SCREEN -> VOID",
            "TERRAIN_LINEAMENT -> CONDUIT",
            "SHOREWARD_ALIGNMENT -> OCEAN_OUTLET",
        ],
    }

    receipts = {
        "morphology_candidates": freeze_json("morphology_candidates", candidate_payload),
        "authoritative_context": freeze_json("authoritative_context", context_payload),
        "falsification_summary": freeze_json("falsification_summary", falsification_payload),
    }
    receipt = {
        "schema": "spiderweb.subsurface.candidate_execution_receipt.v1",
        "benchmark_id": "AGUADILLA_MALEZA_ALTA_SUBSURFACE_001",
        "candidate_count": len(candidates),
        "candidate_id_duplicates": duplicates,
        "candidate_id_nulls": null_ids,
        "source_arithmetic_closed": all(x["closed"] for x in context["source_arithmetic"].values()),
        "all_falsification_closed": falsification_payload["open_falsification_count"] == 0,
        "receipts": receipts,
        "certification": "PROVISIONAL",
    }
    freeze_json("candidate_execution_receipt", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
