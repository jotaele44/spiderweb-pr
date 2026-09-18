from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import requests
import rasterio
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/subsurface_benchmarks/aguadilla_maleza_alta_001.json"
TARGETS = ROOT / "configs/subsurface_benchmarks/aguadilla_maleza_alta_001_acquisition_targets.json"
OUT = ROOT / "artifacts/subsurface/aguadilla_maleza_alta_001"
RAW = OUT / "raw"
DERIVED = OUT / "derived"
RAW.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)

ANCHOR_LON = -67.1140566
ANCHOR_LAT = 18.5091743
Z1 = (-67.1614065, 18.4640016, -67.0667067, 18.5543470)
WINDOWS = {
    "Z1": (-67.1614065, 18.4640016, -67.0667067, 18.5543470),
    "Z2": (-67.1235266, 18.5001398, -67.1045866, 18.5182088),
    "Z3": (-67.1164241, 18.5069157, -67.1116891, 18.5114329),
    "Z4": (-67.1145301, 18.5087226, -67.1135831, 18.5096260),
}

SOURCES = {
    "PRPB_GEOLOGY_3": "https://sige.pr.gov/server/rest/services/MIPR/Geologia_v10_N/FeatureServer/3",
    "PRPB_SINKHOLES_4": "https://sige.pr.gov/server/rest/services/MIPR/Geologia_v10_N/FeatureServer/4",
    "PRPB_CAVES_31": "https://sige.pr.gov/server/rest/services/MIPR/ValorEcologico_v10_N/FeatureServer/31",
    "PRPB_SPRINGS_19": "https://sige.pr.gov/server/rest/services/MIPR/ValorEcologico_v10_N/FeatureServer/19",
    "PRPB_WELLS_JCA_20": "https://sige.pr.gov/server/rest/services/MIPR/ValorEcologico_v10_N/FeatureServer/20",
    "PRPB_WELLS_AAA_21": "https://sige.pr.gov/server/rest/services/MIPR/ValorEcologico_v10_N/FeatureServer/21",
    "PRPB_RIVERS_23": "https://sige.pr.gov/server/rest/services/MIPR/ValorEcologico_v10_N/FeatureServer/23",
    "PRPB_COASTLINE_3": "https://sige.pr.gov/server/rest/services/Advisory_Maps/Advisory_Maps/FeatureServer/3",
}
USGS_MON = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items"
CUDEM = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_PuertoRico_9525/ncei19_n18x50_w067x25_2022v2.tif"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_url(base: str, params: dict[str, object]) -> str:
    return base + "?" + urlencode(sorted((k, str(v).lower() if isinstance(v, bool) else str(v)) for k, v in params.items()))


def freeze_response(source_id: str, url: str, response: requests.Response) -> dict:
    response.raise_for_status()
    raw = response.content
    digest = sha256_bytes(raw)
    path = RAW / f"{source_id}.{digest}.raw"
    if path.exists():
        assert sha256_bytes(path.read_bytes()) == digest
        reused = True
    else:
        path.write_bytes(raw)
        reused = False
    return {
        "source_id": source_id,
        "request_url": url,
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "size_bytes": len(raw),
        "sha256": digest,
        "raw_path": str(path.relative_to(ROOT)),
        "reused_existing_bytes": reused,
    }


def arcgis_query(source_id: str, layer: str, bbox=None, point=None) -> tuple[dict, dict]:
    params: dict[str, object] = {
        "f": "json", "where": "1=1", "outFields": "*", "returnGeometry": True, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "inSR": 4326,
    }
    if point:
        params.update({"geometry": f"{point[0]:.7f},{point[1]:.7f}", "geometryType": "esriGeometryPoint"})
    elif bbox:
        params.update({"geometry": ",".join(f"{v:.7f}" for v in bbox), "geometryType": "esriGeometryEnvelope"})
    else:
        raise ValueError("bbox or point required")
    url = canonical_url(layer.rstrip("/") + "/query", params)
    r = requests.get(url, timeout=120)
    manifest = freeze_response(source_id, url, r)
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(f"{source_id}: {payload['error']}")
    return payload, manifest


def esri_polygon(geom: dict):
    rings = geom.get("rings") or []
    polys = []
    for ring in rings:
        if len(ring) >= 4:
            p = Polygon(ring)
            if p.is_valid and not p.is_empty:
                polys.append(p)
    return unary_union(polys) if polys else None


def esri_lines(geom: dict):
    lines = []
    for path in geom.get("paths") or []:
        if len(path) >= 2:
            lines.append(LineString(path))
    return lines


def validate_feature_set(source_id: str, payload: dict, stable_fields=("OBJECTID",)) -> dict:
    features = payload.get("features") or []
    seen = set()
    null_ids = 0
    dups = 0
    for f in features:
        attrs = f.get("attributes") or {}
        key = tuple(attrs.get(k) for k in stable_fields)
        if all(v is None for v in key):
            null_ids += 1
            continue
        if key in seen:
            dups += 1
        seen.add(key)
    return {"source_id": source_id, "rows": len(features), "unique_ids": len(seen), "null_stable_ids": null_ids, "duplicate_stable_ids": dups}


def exact_geology(payload: dict) -> dict:
    features = payload.get("features") or []
    if len(features) != 1:
        return {"state": "UNRESOLVED", "reason": f"expected 1 intersecting geology polygon, got {len(features)}"}
    f = features[0]
    poly = esri_polygon(f.get("geometry") or {})
    point = Point(ANCHOR_LON, ANCHOR_LAT)
    topology = "UNRESOLVED"
    if poly is not None:
        if point.within(poly):
            topology = "FULLY_WITHIN"
        elif point.touches(poly):
            topology = "TOUCH_ONLY"
        else:
            topology = "OUTSIDE"
    attrs = f.get("attributes") or {}
    state = "VERIFIED" if topology in {"FULLY_WITHIN", "TOUCH_ONLY"} else "UNRESOLVED"
    return {"state": state, "topology": topology, "OBJECTID": attrs.get("OBJECTID"), "formation_raw": attrs.get("HORNBLENDE")}


def download_cudem() -> tuple[Path, dict]:
    meta = requests.get(CUDEM, stream=True, timeout=300)
    meta.raise_for_status()
    temp = RAW / "NOAA_CUDEM.tmp"
    h = hashlib.sha256()
    size = 0
    with temp.open("wb") as fh:
        for chunk in meta.iter_content(chunk_size=8 * 1024 * 1024):
            if chunk:
                fh.write(chunk); h.update(chunk); size += len(chunk)
    digest = h.hexdigest()
    final = RAW / f"NOAA_CUDEM_PR_N18X50_W067X25_2022V2.{digest}.tif"
    if final.exists():
        temp.unlink(missing_ok=True)
        reused = True
    else:
        temp.replace(final); reused = False
    return final, {"source_id": "NOAA_CUDEM_PR_N18X50_W067X25_2022V2", "request_url": CUDEM, "size_bytes": size, "sha256": digest, "raw_path": str(final.relative_to(ROOT)), "reused_existing_bytes": reused}


def terrain_metrics(cudem: Path) -> dict:
    out = {}
    with rasterio.open(cudem) as ds:
        for zid, bbox in WINDOWS.items():
            left, bottom, right, top = bbox
            w = from_bounds(left, bottom, right, top, transform=ds.transform)
            a = ds.read(1, window=w, masked=True).astype("float64")
            z = a.filled(np.nan)
            valid = np.isfinite(z)
            if valid.sum() == 0:
                out[zid] = {"state": "UNRESOLVED", "reason": "no raster cells"}; continue
            xres, yres = abs(ds.transform.a), abs(ds.transform.e)
            # Degrees -> local metres approximation for slope scale.
            m_per_deg_lon = 111320.0 * math.cos(math.radians(ANCHOR_LAT))
            m_per_deg_lat = 110574.0
            dx = max(xres * m_per_deg_lon, 0.1); dy = max(yres * m_per_deg_lat, 0.1)
            fill = np.where(valid, z, np.nanmedian(z[valid]))
            gy, gx = np.gradient(fill, dy, dx)
            slope = np.degrees(np.arctan(np.hypot(gx, gy)))
            lap = ndimage.laplace(fill)
            local_min = fill == ndimage.minimum_filter(fill, size=5, mode="nearest")
            local_max = ndimage.maximum_filter(fill, size=11, mode="nearest")
            prominence = local_max - fill
            depression_mask = local_min & valid & (prominence >= 0.5)
            # D8-like steepest lower-neighbour terminal/sink screening.
            sink_mask = np.ones(fill.shape, dtype=bool)
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    if oy == 0 and ox == 0: continue
                    shifted = np.roll(np.roll(fill, oy, axis=0), ox, axis=1)
                    sink_mask &= fill <= shifted
            sink_mask &= valid
            curvature_threshold = float(np.nanpercentile(np.abs(lap[valid]), 99.5))
            lineament_mask = valid & (np.abs(lap) >= curvature_threshold)
            out[zid] = {
                "state": "OBSERVED_DERIVED",
                "cells": int(valid.sum()),
                "elevation_min_m": float(np.nanmin(z)), "elevation_max_m": float(np.nanmax(z)), "elevation_mean_m": float(np.nanmean(z)),
                "slope_p50_deg": float(np.nanpercentile(slope[valid], 50)), "slope_p95_deg": float(np.nanpercentile(slope[valid], 95)),
                "depression_candidate_cells": int(depression_mask.sum()), "d8_sink_candidate_cells": int(sink_mask.sum()),
                "terrain_lineament_candidate_cells": int(lineament_mask.sum()),
                "interpretive_boundary": "derived morphology candidates only; not cave/void/conduit identity",
            }
    return out


def coastline_corridor(coast_payload: dict) -> dict:
    lines = []
    for f in coast_payload.get("features") or []:
        lines.extend(esri_lines(f.get("geometry") or {}))
    if not lines:
        return {"state": "UNRESOLVED", "reason": "no coastline linework"}
    coast = unary_union(lines)
    p = Point(ANCHOR_LON, ANCHOR_LAT)
    q = nearest_points(p, coast)[1]
    to_utm = Transformer.from_crs(4326, 32619, always_xy=True)
    to_wgs = Transformer.from_crs(32619, 4326, always_xy=True)
    ax, ay = to_utm.transform(p.x, p.y); qx, qy = to_utm.transform(q.x, q.y)
    vx, vy = qx - ax, qy - ay; length = math.hypot(vx, vy)
    if length == 0:
        return {"state": "UNRESOLVED", "reason": "anchor lies on shoreline"}
    ux, uy = vx/length, vy/length
    offshore_x, offshore_y = qx + ux * 2000.0, qy + uy * 2000.0
    ox, oy = to_wgs.transform(offshore_x, offshore_y)
    return {"state": "CANDIDATE", "shoreline_nearest": [q.x, q.y], "anchor_to_shore_m": length, "offshore_terminal": [ox, oy], "offshore_extension_m": 2000.0, "identity_boundary": "straight screening corridor; not a subsurface conduit"}


def sentinel_temporal_metadata() -> dict:
    endpoint = "https://earth-search.aws.element84.com/v1/search"
    epochs = ["2018-01-01/2018-12-31", "2020-01-01/2020-12-31", "2022-01-01/2022-12-31", "2024-01-01/2024-12-31", "2026-01-01/2026-12-31"]
    rows = []
    for epoch in epochs:
        body = {"collections": ["sentinel-2-l2a"], "bbox": list(WINDOWS["Z3"]), "datetime": epoch, "limit": 50, "query": {"eo:cloud_cover": {"lt": 25}}}
        r = requests.post(endpoint, json=body, timeout=120); r.raise_for_status()
        raw = r.content; digest = sha256_bytes(raw)
        (RAW / f"EARTH_SEARCH_{epoch[:4]}.{digest}.json").write_bytes(raw)
        features = r.json().get("features") or []
        features.sort(key=lambda x: (x.get("properties", {}).get("eo:cloud_cover", 999), x.get("id", "")))
        best = features[0] if features else None
        rows.append({"epoch": epoch, "candidate_count": len(features), "selected_id": None if best is None else best.get("id"), "cloud_cover": None if best is None else best.get("properties", {}).get("eo:cloud_cover"), "state": "OBSERVED_METADATA" if best else "UNRESOLVED"})
    return {"provider": "Element84 Earth Search Sentinel-2 L2A", "epochs": rows, "pixel_persistence_state": "UNRESOLVED", "note": "catalog persistence is frozen; pixel-level temporal classification requires separately frozen image assets"}


def main() -> int:
    manifests = []
    validations = []
    payloads = {}
    for sid, endpoint in SOURCES.items():
        if sid == "PRPB_GEOLOGY_3":
            p, m = arcgis_query(sid, endpoint, point=(ANCHOR_LON, ANCHOR_LAT))
        else:
            p, m = arcgis_query(sid, endpoint, bbox=Z1)
        payloads[sid] = p; manifests.append(m)
        validations.append(validate_feature_set(sid, p, ("OBJECTID",)))

    params = {"bbox": ",".join(f"{v:.7f}" for v in Z1), "limit": 10000, "f": "json", "state_code": "72"}
    u = canonical_url(USGS_MON, params)
    r = requests.get(u, timeout=120)
    manifests.append(freeze_response("USGS_MONITORING_LOCATIONS_PR", u, r))
    usgs = r.json(); validations.append({"source_id": "USGS_MONITORING_LOCATIONS_PR", "rows": len(usgs.get("features") or []), "duplicate_stable_ids": 0, "null_stable_ids": sum(1 for f in usgs.get("features") or [] if not f.get("id"))})

    cudem, cudem_manifest = download_cudem(); manifests.append(cudem_manifest)
    terrain = terrain_metrics(cudem)
    geology = exact_geology(payloads["PRPB_GEOLOGY_3"])
    corridor = coastline_corridor(payloads["PRPB_COASTLINE_3"])
    temporal = sentinel_temporal_metadata()

    all_unique = all(v.get("duplicate_stable_ids", 0) == 0 and v.get("null_stable_ids", 0) == 0 for v in validations)
    required_rows = {sid: len(payloads[sid].get("features") or []) for sid in payloads}
    unresolved = []
    if geology.get("state") != "VERIFIED": unresolved.append("exact_geology")
    if corridor.get("state") == "UNRESOLVED": unresolved.append("coastline_corridor")
    if temporal.get("pixel_persistence_state") != "VERIFIED": unresolved.append("pixel_temporal_persistence")
    if not all_unique: unresolved.append("stable_id_integrity")

    result = {
        "schema": "spiderweb.subsurface.aguadilla_execution.v1",
        "benchmark_id": "AGUADILLA_MALEZA_ALTA_SUBSURFACE_001",
        "geology_binding": geology,
        "source_validations": validations,
        "source_rows": required_rows,
        "terrain_windows": terrain,
        "coastal_corridor": corridor,
        "temporal_persistence": temporal,
        "unresolved": sorted(unresolved),
        "certification": "PASS" if not unresolved else "PROVISIONAL",
        "identity_boundary": "No derived depression, lineament, corridor or offshore alignment verifies a cave, void, conduit, spring or ocean outlet without independent identity evidence.",
    }
    (DERIVED / "execution.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    manifest_obj = {"schema": "spiderweb.subsurface.evidence_manifest.v1", "sources": sorted(manifests, key=lambda x: x["source_id"])}
    canonical = json.dumps(manifest_obj, sort_keys=True, separators=(",", ":")).encode()
    manifest_obj["logical_sha256"] = sha256_bytes(canonical)
    (OUT / "manifest.json").write_text(json.dumps(manifest_obj, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"certification": result["certification"], "unresolved": result["unresolved"], "manifest_sha256": manifest_obj["logical_sha256"], "geology": geology, "corridor": corridor}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
