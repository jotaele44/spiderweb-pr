#!/usr/bin/env python3
"""Byte-freeze EX1502L3 XYZ and test observations against valid W00247 BAG cells."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.warp import transform as transform_xy

W00247_URL = "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00247/BAG/W00247_MB_VR_MLLW_3of4.bag"
EX1502L3_XYZ_URL = "https://data.ngdc.noaa.gov/platforms/ocean/ships/okeanos_explorer/EX1502L3/multibeam/data/version1/products/EX1502L3_MB_FNL_50m_WGS84.xyz.gz"
EX1502L3_ISO_URL = "https://www.ngdc.noaa.gov/metadata/published/NOAA/NESDIS/NGDC/MGG/Multibeam/iso/xml/EX1502L3_Multibeam.xml"
OUT = Path("evidence/marine/ex1502l3_w00247_overlap_v0_1")


def _download(url: str, path: Path) -> tuple[str, int, str | None]:
    h = hashlib.sha256()
    size = 0
    req = Request(url, headers={"User-Agent": "spiderweb-pr/0.1 marine-evidence"})
    with urlopen(req, timeout=180) as response, path.open("wb") as f:
        content_type = response.headers.get("Content-Type")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size, content_type


def _metadata_snippets(text: str) -> list[str]:
    snippets: list[str] = []
    for match in re.finditer(r"(?i)(vertical|datum|depth|elevation|reference)", text):
        start = max(0, match.start() - 180)
        end = min(len(text), match.end() + 300)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        if snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= 60:
            break
    return snippets


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bag_path = OUT / "W00247_MB_VR_MLLW_3of4.bag"
    xyz_path = OUT / "EX1502L3_MB_FNL_50m_WGS84.xyz.gz"
    iso_path = OUT / "EX1502L3_Multibeam.xml"

    bag_sha, bag_size, bag_type = _download(W00247_URL, bag_path)
    xyz_sha, xyz_size, xyz_type = _download(EX1502L3_XYZ_URL, xyz_path)
    iso_sha, iso_size, iso_type = _download(EX1502L3_ISO_URL, iso_path)

    with rasterio.open(bag_path) as ds:
        if ds.crs is None:
            raise ValueError("W00247 BAG missing CRS")
        if abs(ds.transform.b) > 1e-12 or abs(ds.transform.d) > 1e-12:
            raise ValueError("rotated BAG transform unsupported in bounded overlap pass")
        valid = ds.read_masks(1) > 0
        bag_valid_cells = int(valid.sum())
        bag_crs = ds.crs.to_string()
        bag_bounds_native = [float(ds.bounds.left), float(ds.bounds.bottom), float(ds.bounds.right), float(ds.bounds.top)]
        bag_transform = ds.transform
        bag_width = ds.width
        bag_height = ds.height
        bag_tags = ds.tags()
        band_tags = ds.tags(1)
        wgs_bounds = rasterio.warp.transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)

    min_lon, min_lat, max_lon, max_lat = (float(v) for v in wgs_bounds)
    total_numeric_rows = 0
    bbox_rows = 0
    valid_cell_rows = 0
    touched_cells: set[tuple[int, int]] = set()
    overlap_depth_min: float | None = None
    overlap_depth_max: float | None = None
    parse_reject_rows = 0

    chunk_lon: list[float] = []
    chunk_lat: list[float] = []
    chunk_z: list[float] = []

    def consume() -> None:
        nonlocal valid_cell_rows, overlap_depth_min, overlap_depth_max
        if not chunk_lon:
            return
        xs, ys = transform_xy("EPSG:4326", bag_crs, chunk_lon, chunk_lat)
        xs_a = np.asarray(xs, dtype=float)
        ys_a = np.asarray(ys, dtype=float)
        cols = np.floor((xs_a - bag_transform.c) / bag_transform.a).astype(np.int64)
        rows = np.floor((ys_a - bag_transform.f) / bag_transform.e).astype(np.int64)
        zs = np.asarray(chunk_z, dtype=float)
        inside = (rows >= 0) & (rows < bag_height) & (cols >= 0) & (cols < bag_width)
        idxs = np.nonzero(inside)[0]
        for i in idxs:
            r = int(rows[i]); c = int(cols[i])
            if not valid[r, c]:
                continue
            z = float(zs[i])
            valid_cell_rows += 1
            touched_cells.add((r, c))
            overlap_depth_min = z if overlap_depth_min is None else min(overlap_depth_min, z)
            overlap_depth_max = z if overlap_depth_max is None else max(overlap_depth_max, z)
        chunk_lon.clear(); chunk_lat.clear(); chunk_z.clear()

    with gzip.open(xyz_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().replace(",", " ").split()
            if len(parts) < 3:
                parse_reject_rows += 1
                continue
            try:
                lon, lat, z = map(float, parts[:3])
            except ValueError:
                parse_reject_rows += 1
                continue
            total_numeric_rows += 1
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            bbox_rows += 1
            chunk_lon.append(lon); chunk_lat.append(lat); chunk_z.append(z)
            if len(chunk_lon) >= 20000:
                consume()
        consume()

    iso_text = iso_path.read_text(encoding="utf-8", errors="replace")
    snippets = _metadata_snippets(iso_text)

    vertical_binding = {
        "w00247": "MLLW / EPSG:5866 (certified from BAG product metadata in the prior W00247 byte pass)",
        "ex1502l3": "UNRESOLVED_FROM_CURRENT_PRODUCT_METADATA",
        "depth_subtraction_allowed": False,
        "reason": "The processed EX1502L3 grid is horizontally labeled WGS84, but this bounded pass does not infer a vertical datum from the filename. Direct numerical depth subtraction remains blocked until an explicit authoritative vertical reference is bound.",
    }

    manifest = {
        "receipt_version": "0.1",
        "w00247": {
            "survey_id": "W00247",
            "url": W00247_URL,
            "filename": bag_path.name,
            "sha256": bag_sha,
            "size_bytes": bag_size,
            "content_type": bag_type,
            "crs": bag_crs,
            "bounds_native": bag_bounds_native,
            "bounds_wgs84": list(wgs_bounds),
            "valid_cells": bag_valid_cells,
            "dataset_tags": bag_tags,
            "band_1_tags": band_tags,
        },
        "candidate": {
            "survey_id": "EX1502L3",
            "sensor_root": "Kongsberg EM302 / Okeanos Explorer / EX1502L3 / 2015",
            "xyz_url": EX1502L3_XYZ_URL,
            "xyz_sha256": xyz_sha,
            "xyz_size_bytes": xyz_size,
            "xyz_content_type": xyz_type,
            "iso_url": EX1502L3_ISO_URL,
            "iso_sha256": iso_sha,
            "iso_size_bytes": iso_size,
            "iso_content_type": iso_type,
            "iso_vertical_reference_snippets": snippets,
        },
        "overlap": {
            "xyz_numeric_rows": total_numeric_rows,
            "xyz_parse_reject_rows": parse_reject_rows,
            "xyz_rows_inside_w00247_raster_bbox": bbox_rows,
            "xyz_rows_on_valid_w00247_bag_cells": valid_cell_rows,
            "unique_w00247_valid_cells_touched": len(touched_cells),
            "candidate_depth_min": overlap_depth_min,
            "candidate_depth_max": overlap_depth_max,
        },
        "vertical_binding": vertical_binding,
        "independent_sensor_root": "PASS" if valid_cell_rows > 0 else "REJECTED_NO_VALID_CELL_OVERLAP",
        "state": "PASS_SECOND_SENSOR_ROOT" if valid_cell_rows > 0 else "NO_OVERLAP",
        "certification_boundary": "A PASS_SECOND_SENSOR_ROOT result certifies byte identity and nonzero spatial overlap between a distinct EX1502L3 multibeam acquisition root and valid W00247 BAG cells. It does not certify vertical-datum equivalence, numerical depth agreement, screenshot equivalence, or geomorphic-feature identity.",
    }
    (OUT / "overlap_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
