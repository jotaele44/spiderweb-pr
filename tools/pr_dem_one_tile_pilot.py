#!/usr/bin/env python3
"""One-tile Puerto Rico DEM terrain-screening pilot.

Reads one GeoTIFF DEM, downsamples it, finds flat terrain patches with steeper
surroundings, and writes CSV/GeoJSON outputs. This is a bounded file-processing
pilot used after the PR_Geodata integrity audit.

Requires: rasterio, numpy. Optional: scipy for faster connected components.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as crs_transform

try:
    from scipy import ndimage as ndi
except Exception:
    ndi = None


CSV_COLUMNS = [
    "candidate_id",
    "source_tile",
    "crs",
    "x",
    "y",
    "lon",
    "lat",
    "pixel_count",
    "area_m2",
    "mean_elevation_m",
    "mean_slope_deg",
    "ring_mean_slope_deg",
    "tpi_mean_m",
    "score_flat_patch",
    "score_edge_contrast",
    "score_high_local_position",
    "ILAP_SCORE",
    "review_class",
]


def review_class(score: int) -> str:
    if score <= 30:
        return "Background"
    if score <= 50:
        return "Review"
    if score <= 70:
        return "Candidate"
    return "High Priority"


def fill_nodata(arr: np.ndarray, nodata: Optional[float]) -> np.ndarray:
    data = arr.astype("float64", copy=False)
    if nodata is not None:
        data = np.where(data == nodata, np.nan, data)
    if not np.isfinite(data).any():
        raise ValueError("DEM has no finite elevation values")
    return np.where(np.isfinite(data), data, float(np.nanmedian(data)))


def pick_utm_epsg(lon: float) -> int:
    """NAD83 UTM EPSG code for a Puerto Rico longitude.

    EPSG:269NN encodes NAD83 / UTM zone NN North (NN = ``26900 + zone``). For PR
    this resolves to 26919 (zone 19N, west of -66 deg) or 26920 (zone 20N,
    Vieques/Culebra and the eastern edge) — the two zones the geodata integrity
    audit expects (``tools/pr_geodata_integrity_audit.py`` EXPECTED_DEM_CRS).
    """

    zone = int((lon + 180.0) / 6.0) + 1
    return 26900 + zone


def read_dem(
    path: Path,
    target_resolution_m: float,
    *,
    reproject: bool = True,
    target_crs: str = "auto",
    assume_source_crs: Optional[str] = None,
) -> Tuple[np.ndarray, Affine, str, Dict[str, object]]:
    """Read a DEM tile, downsampling to roughly ``target_resolution_m`` metres.

    The downsample factor, slope, and pixel-area math all assume ``transform``
    units are metres. A geographic tile (e.g. the EPSG:4269 NAD83 CUDEM) is
    therefore reprojected on the fly to a metre-based CRS (NAD83 UTM, per
    ``pick_utm_epsg``) via a WarpedVRT before that math runs; already-projected
    tiles are read unchanged. Pass ``reproject=False`` to opt out.
    """

    with rasterio.open(path) as src:
        source_crs = src.crs
        if source_crs is None and assume_source_crs:
            source_crs = CRS.from_user_input(assume_source_crs)
        if source_crs is None:
            raise SystemExit(
                f"DEM tile has no CRS and --assume-source-crs was not given: {path}"
            )

        reprojected_to: Optional[str] = None
        vrt: Optional[WarpedVRT] = None
        try:
            dataset: object = src
            effective_crs = source_crs
            if reproject and source_crs.is_geographic:
                if target_crs and target_crs != "auto":
                    dst_crs = CRS.from_user_input(target_crs)
                else:
                    bounds = src.bounds
                    center_lon = (float(bounds.left) + float(bounds.right)) / 2.0
                    dst_crs = CRS.from_epsg(pick_utm_epsg(center_lon))
                # Pass src_crs explicitly so an --assume-source-crs tile (whose
                # src.crs is None) still has a source CRS to warp from.
                vrt = WarpedVRT(
                    src, src_crs=source_crs, crs=dst_crs, resampling=Resampling.bilinear
                )
                dataset = vrt
                effective_crs = dst_crs
                reprojected_to = dst_crs.to_string()

            native = max(abs(float(dataset.transform.a)), abs(float(dataset.transform.e)))
            scale = max(1.0, float(target_resolution_m) / native)
            out_width = max(1, int(round(dataset.width / scale)))
            out_height = max(1, int(round(dataset.height / scale)))
            arr = dataset.read(
                1, out_shape=(out_height, out_width), resampling=Resampling.bilinear, masked=False
            )
            transform = dataset.transform * Affine.scale(
                dataset.width / out_width, dataset.height / out_height
            )
            # Use the effective source/target CRS, not dataset.crs — the latter is
            # None for a CRS-less tile read with --assume-source-crs.
            crs = effective_crs.to_string()
            nodata = dataset.nodata
        finally:
            if vrt is not None:
                vrt.close()

        meta = {
            "source_width": src.width,
            "source_height": src.height,
            "source_crs": source_crs.to_string(),
            "reprojected_to": reprojected_to,
            "processing_crs": crs,
            "output_width": out_width,
            "output_height": out_height,
            "output_resolution_x": abs(float(transform.a)),
            "output_resolution_y": abs(float(transform.e)),
        }
        return fill_nodata(arr, nodata), transform, crs, meta


def slope_deg(dem: np.ndarray, transform: Affine) -> np.ndarray:
    dx = abs(float(transform.a))
    dy = abs(float(transform.e))
    gy, gx = np.gradient(dem, dy, dx)
    return np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy)))


def mean_filter(arr: np.ndarray, size: int) -> np.ndarray:
    size = max(3, int(size) | 1)
    if ndi is not None:
        return ndi.uniform_filter(arr, size=size, mode="nearest")
    pad = size // 2
    padded = np.pad(arr, pad, mode="edge")
    out = np.empty_like(arr, dtype="float64")
    for r in range(arr.shape[0]):
        for c in range(arr.shape[1]):
            window = padded[r : r + size, c : c + size]
            out[r, c] = float(np.mean(window))
    return out


def label_mask(mask: np.ndarray) -> Tuple[np.ndarray, int]:
    if ndi is not None:
        labels, n = ndi.label(mask)
        return labels.astype("int32"), int(n)
    labels = np.zeros(mask.shape, dtype="int32")
    n = 0
    for r in range(mask.shape[0]):
        for c in range(mask.shape[1]):
            if not mask[r, c] or labels[r, c]:
                continue
            n += 1
            q = deque([(r, c)])
            labels[r, c] = n
            while q:
                rr, cc = q.popleft()
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = rr + dr, cc + dc
                    if 0 <= nr < mask.shape[0] and 0 <= nc < mask.shape[1] and mask[nr, nc] and not labels[nr, nc]:
                        labels[nr, nc] = n
                        q.append((nr, nc))
    return labels, n


def dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    if ndi is not None:
        return ndi.binary_dilation(mask, iterations=iterations)
    out = mask.copy()
    for _ in range(iterations):
        p = np.pad(out, 1, mode="constant", constant_values=False)
        out = (
            p[:-2, :-2] | p[:-2, 1:-1] | p[:-2, 2:] |
            p[1:-1, :-2] | p[1:-1, 1:-1] | p[1:-1, 2:] |
            p[2:, :-2] | p[2:, 1:-1] | p[2:, 2:]
        )
    return out


def xy_lonlat(transform: Affine, rows: np.ndarray, cols: np.ndarray, crs: str) -> Tuple[float, float, Optional[float], Optional[float]]:
    x, y = transform * (float(np.mean(cols)) + 0.5, float(np.mean(rows)) + 0.5)
    if crs and crs != "UNKNOWN" and crs != "EPSG:4326":
        try:
            lon, lat = crs_transform(crs, "EPSG:4326", [x], [y])
            return float(x), float(y), float(lon[0]), float(lat[0])
        except Exception:
            pass
    if crs == "EPSG:4326":
        return float(x), float(y), float(x), float(y)
    return float(x), float(y), None, None


def extract_rows(dem: np.ndarray, transform: Affine, crs: str, source_tile: Path, args: argparse.Namespace) -> List[Dict[str, object]]:
    slope = slope_deg(dem, transform)
    tpi = dem - mean_filter(dem, args.tpi_window_pixels)
    flat = slope <= args.internal_slope_max
    labels, count = label_mask(flat)
    pixel_area = abs(float(transform.a) * float(transform.e))
    rows_out: List[Dict[str, object]] = []

    for label in range(1, count + 1):
        patch = labels == label
        pixels = int(patch.sum())
        area = pixels * pixel_area
        if area < args.min_area_m2 or area > args.max_area_m2:
            continue
        ring = dilate(patch, args.ring_pixels) & ~patch
        if not ring.any():
            continue
        ring_slope = float(np.mean(slope[ring]))
        if ring_slope < args.surrounding_slope_min:
            continue
        rr, cc = np.where(patch)
        x, y, lon, lat = xy_lonlat(transform, rr, cc, crs)
        patch_slope = float(np.mean(slope[patch]))
        tpi_mean = float(np.mean(tpi[patch]))

        score_flat = 20 if ring_slope >= args.surrounding_slope_min else int(round(20 * ring_slope / args.surrounding_slope_min))
        score_edge = int(max(0, min(15, round(ring_slope - patch_slope))))
        score_high = int(max(0, min(10, round(max(0.0, tpi_mean) / 3.0 * 10))))
        total = int(score_flat + score_edge + score_high)

        rows_out.append({
            "candidate_id": f"{source_tile.stem}_{label:06d}",
            "source_tile": str(source_tile),
            "crs": crs,
            "x": x,
            "y": y,
            "lon": lon,
            "lat": lat,
            "pixel_count": pixels,
            "area_m2": round(area, 3),
            "mean_elevation_m": round(float(np.mean(dem[patch])), 3),
            "mean_slope_deg": round(patch_slope, 3),
            "ring_mean_slope_deg": round(ring_slope, 3),
            "tpi_mean_m": round(tpi_mean, 3),
            "score_flat_patch": score_flat,
            "score_edge_contrast": score_edge,
            "score_high_local_position": score_high,
            "ILAP_SCORE": total,
            "review_class": review_class(total),
        })

    rows_out.sort(key=lambda r: (int(r["ILAP_SCORE"]), float(r["area_m2"])), reverse=True)
    return rows_out[: args.max_candidates]


def write_csv(rows: List[Dict[str, object]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_geojson(rows: List[Dict[str, object]], path: Path) -> None:
    features = []
    for row in rows:
        lon, lat = row.get("lon"), row.get("lat")
        coords = [lon, lat] if lon is not None and lat is not None else [row["x"], row["y"]]
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": coords}, "properties": row})
    payload = {"type": "FeatureCollection", "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "features": features}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a one-tile DEM terrain-screening pilot.")
    p.add_argument("--dem-tile", required=True)
    p.add_argument("--output-dir", default="outputs/pr_dem_one_tile_pilot")
    p.add_argument("--target-resolution-m", type=float, default=5.0)
    p.add_argument("--internal-slope-max", type=float, default=3.0)
    p.add_argument("--surrounding-slope-min", type=float, default=15.0)
    p.add_argument("--min-area-m2", type=float, default=100.0)
    p.add_argument("--max-area-m2", type=float, default=5000.0)
    p.add_argument("--ring-pixels", type=int, default=5)
    p.add_argument("--tpi-window-pixels", type=int, default=21)
    p.add_argument("--max-candidates", type=int, default=500)
    p.add_argument(
        "--no-reproject",
        dest="reproject",
        action="store_false",
        help="Do not reproject geographic tiles; process pixels in their native CRS.",
    )
    p.set_defaults(reproject=True)
    p.add_argument(
        "--target-crs",
        default="auto",
        help="Metre-based CRS to reproject geographic tiles to (e.g. EPSG:26919). "
        "'auto' picks NAD83 UTM 19N/20N from the tile centroid.",
    )
    p.add_argument(
        "--assume-source-crs",
        default=None,
        help="CRS to assume when a tile has no embedded CRS (e.g. EPSG:4269).",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    dem_tile = Path(args.dem_tile).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not dem_tile.exists() or dem_tile.stat().st_size == 0:
        raise SystemExit(f"DEM tile missing or empty: {dem_tile}")

    dem, transform, crs, meta = read_dem(
        dem_tile,
        args.target_resolution_m,
        reproject=args.reproject,
        target_crs=args.target_crs,
        assume_source_crs=args.assume_source_crs,
    )
    rows = extract_rows(dem, transform, crs, dem_tile, args)

    csv_path = output_dir / "pr_dem_one_tile_candidates.csv"
    geojson_path = output_dir / "pr_dem_one_tile_candidates.geojson"
    manifest_path = output_dir / "pr_dem_one_tile_manifest.json"
    write_csv(rows, csv_path)
    write_geojson(rows, geojson_path)
    manifest_path.write_text(json.dumps({
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_tile": str(dem_tile),
        "dem_metadata": meta,
        "candidate_count": len(rows),
        "score_columns": ["score_flat_patch", "score_edge_contrast", "score_high_local_position"],
        "score_rule": "ILAP_SCORE = score_flat_patch + score_edge_contrast + score_high_local_position",
    }, indent=2), encoding="utf-8")

    print(f"CSV: {csv_path}")
    print(f"GeoJSON: {geojson_path}")
    print(f"Manifest: {manifest_path}")
    print(f"Candidate rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
