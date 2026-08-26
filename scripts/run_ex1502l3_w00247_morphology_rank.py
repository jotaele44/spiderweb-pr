#!/usr/bin/env python3
"""Compare collocated morphology ordering without cross-datum depth subtraction."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as transform_xy

ROOT = Path("evidence/marine/ex1502l3_w00247_overlap_v0_1")
BAG = ROOT / "W00247_MB_VR_MLLW_3of4.bag"
XYZ = ROOT / "EX1502L3_MB_FNL_50m_WGS84.xyz.gz"
OUT = Path("evidence/marine/ex1502l3_w00247_morphology_rank_v0_1")


def _rank_average(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1.0
        ranks[order[i:j]] = avg
        i = j
    return ranks


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2:
        return None
    da = a - a.mean(); db = b - b.mean()
    denom = float(np.sqrt(np.sum(da * da) * np.sum(db * db)))
    if denom == 0.0:
        return None
    return float(np.sum(da * db) / denom)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(BAG) as ds:
        if ds.crs is None:
            raise ValueError("W00247 BAG missing CRS")
        if abs(ds.transform.b) > 1e-12 or abs(ds.transform.d) > 1e-12:
            raise ValueError("rotated BAG transform unsupported")
        values = ds.read(1)
        valid = ds.read_masks(1) > 0
        transform = ds.transform
        crs = ds.crs.to_string()
        width = ds.width; height = ds.height
        bounds = rasterio.warp.transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)

    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bounds)
    sums: dict[tuple[int, int], float] = {}
    counts: dict[tuple[int, int], int] = {}
    chunk_lon: list[float] = []
    chunk_lat: list[float] = []
    chunk_z: list[float] = []

    def consume() -> None:
        if not chunk_lon:
            return
        xs, ys = transform_xy("EPSG:4326", crs, chunk_lon, chunk_lat)
        xs_a = np.asarray(xs, dtype=float); ys_a = np.asarray(ys, dtype=float)
        cols = np.floor((xs_a - transform.c) / transform.a).astype(np.int64)
        rows = np.floor((ys_a - transform.f) / transform.e).astype(np.int64)
        zs = np.asarray(chunk_z, dtype=float)
        inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
        for i in np.nonzero(inside)[0]:
            r = int(rows[i]); c = int(cols[i])
            if not valid[r, c]:
                continue
            key = (r, c)
            sums[key] = sums.get(key, 0.0) + float(zs[i])
            counts[key] = counts.get(key, 0) + 1
        chunk_lon.clear(); chunk_lat.clear(); chunk_z.clear()

    with gzip.open(XYZ, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().replace(",", " ").split()
            if len(parts) < 3:
                continue
            try:
                lon, lat, z = map(float, parts[:3])
            except ValueError:
                continue
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
            chunk_lon.append(lon); chunk_lat.append(lat); chunk_z.append(z)
            if len(chunk_lon) >= 20000:
                consume()
        consume()

    rows_out: list[dict[str, object]] = []
    bag_vals: list[float] = []
    ex_vals: list[float] = []
    for (r, c) in sorted(sums):
        if counts[(r, c)] <= 0:
            continue
        b = float(values[r, c])
        e = float(sums[(r, c)] / counts[(r, c)])
        bag_vals.append(b); ex_vals.append(e)
        rows_out.append({"row": r, "col": c, "w00247_value": b, "ex1502l3_mean_value": e, "ex1502l3_point_count": counts[(r, c)]})

    bag_a = np.asarray(bag_vals, dtype=float)
    ex_a = np.asarray(ex_vals, dtype=float)
    rho = _pearson(_rank_average(bag_a), _rank_average(ex_a)) if len(bag_a) >= 2 else None
    same_order_fraction = None
    if len(bag_a) >= 3:
        bag_d = np.diff(bag_a)
        ex_d = np.diff(ex_a)
        nz = (bag_d != 0) & (ex_d != 0)
        if np.any(nz):
            same_order_fraction = float(np.mean(np.sign(bag_d[nz]) == np.sign(ex_d[nz])))

    with (OUT / "paired_cells.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "col", "w00247_value", "ex1502l3_mean_value", "ex1502l3_point_count"])
        writer.writeheader(); writer.writerows(rows_out)

    manifest = {
        "receipt_version": "0.1",
        "paired_valid_bag_cells": len(rows_out),
        "spearman_rank_rho": rho,
        "sequential_same_order_fraction": same_order_fraction,
        "w00247_value_range": [float(bag_a.min()), float(bag_a.max())] if len(bag_a) else None,
        "ex1502l3_value_range": [float(ex_a.min()), float(ex_a.max())] if len(ex_a) else None,
        "comparison_semantics": "Rank/order association only. No W00247-minus-EX1502L3 depth residual, offset, RMSE, or datum transformation is computed.",
        "vertical_gate": "BLOCKED_CONTRADICTORY_EX1502L3_METADATA",
        "feature_promotion": "NOT_PERMITTED_FROM_THIS_STATISTIC_ALONE",
        "state": "PASS_COMPUTED_ASSOCIATION" if len(rows_out) >= 2 and rho is not None else "UNRESOLVED",
        "certification_boundary": "This statistic tests whether collocated elevations/depth-like values preserve ordering across two distinct acquisition roots. It is not a vertical-datum equivalence test and cannot by itself certify a geomorphic feature or screenshot match.",
    }
    (OUT / "morphology_rank_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
