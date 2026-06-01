#!/usr/bin/env python3
"""Batch runner for Puerto Rico DEM terrain-screening pilots.

This script discovers DEM GeoTIFF tiles, selects a bounded region, runs the
one-tile pilot on each selected tile, merges the CSV/GeoJSON outputs, and writes
a batch manifest.

Default named profile: arecibo_utuado.
The profile is a broad operational bbox, not a legal municipal boundary.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import rasterio
from rasterio.warp import transform_bounds


PROFILES = {
    "arecibo_utuado": {
        "label": "Arecibo / Utuado broad pilot bbox",
        "bbox_wgs84": [-66.98, 18.12, -66.43, 18.56],
        "note": "Broad operational bbox for first batch testing; not a legal municipal boundary.",
    }
}

ONE_TILE_CSV = "pr_dem_one_tile_candidates.csv"
ONE_TILE_GEOJSON = "pr_dem_one_tile_candidates.geojson"
ONE_TILE_MANIFEST = "pr_dem_one_tile_manifest.json"
MERGED_CSV = "pr_dem_batch_candidates.csv"
MERGED_GEOJSON = "pr_dem_batch_candidates.geojson"
SELECTED_TILES_CSV = "selected_tiles.csv"
BATCH_MANIFEST = "batch_manifest.json"
SCORE_SUM_REPORT = "batch_score_sum_check.json"

SCORE_COLUMNS = ["score_flat_patch", "score_edge_contrast", "score_high_local_position"]


def parse_bbox(value: str) -> List[float]:
    parts = [float(x.strip()) for x in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be west,south,east,north")
    west, south, east, north = parts
    if west >= east or south >= north:
        raise argparse.ArgumentTypeError("bbox must satisfy west < east and south < north")
    return parts


def intersects(a: Sequence[float], b: Sequence[float]) -> bool:
    aw, a_s, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and a_s <= bn and an >= bs


def discover_dem_tiles(dem_dir: Path) -> List[Path]:
    return sorted(
        p for p in dem_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {".tif", ".tiff"}
        and not p.name.lower().endswith((".ovr", ".aux.xml"))
    )


def tile_wgs84_bounds(tile: Path) -> Tuple[List[float], Dict[str, object]]:
    with rasterio.open(tile) as src:
        crs = src.crs.to_string() if src.crs else "UNKNOWN"
        bounds = list(src.bounds)
        if src.crs and crs != "EPSG:4326":
            west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
            bbox = [float(west), float(south), float(east), float(north)]
        else:
            bbox = [float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])]
        meta = {
            "path": str(tile),
            "name": tile.name,
            "crs": crs,
            "source_bounds": bounds,
            "bbox_wgs84": bbox,
            "width": src.width,
            "height": src.height,
            "size_bytes": tile.stat().st_size,
        }
        return bbox, meta


def select_tiles(dem_dir: Path, bbox_wgs84: Sequence[float], max_tiles: int) -> List[Dict[str, object]]:
    selected: List[Dict[str, object]] = []
    for tile in discover_dem_tiles(dem_dir):
        bbox, meta = tile_wgs84_bounds(tile)
        if intersects(bbox, bbox_wgs84):
            selected.append(meta)
    selected.sort(key=lambda x: str(x["name"]))
    if max_tiles and max_tiles > 0:
        selected = selected[:max_tiles]
    return selected


def write_selected_tiles(rows: Sequence[Dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["index", "name", "path", "crs", "bbox_wgs84", "width", "height", "size_bytes"]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            writer.writerow({
                "index": i,
                "name": row["name"],
                "path": row["path"],
                "crs": row["crs"],
                "bbox_wgs84": json.dumps(row["bbox_wgs84"]),
                "width": row["width"],
                "height": row["height"],
                "size_bytes": row["size_bytes"],
            })


def run_one_tile(repo_root: Path, tile_path: Path, output_dir: Path, args: argparse.Namespace) -> int:
    script = repo_root / "tools" / "pr_dem_one_tile_pilot.py"
    cmd = [
        sys.executable,
        str(script),
        "--dem-tile",
        str(tile_path),
        "--output-dir",
        str(output_dir),
        "--target-resolution-m",
        str(args.target_resolution_m),
        "--internal-slope-max",
        str(args.internal_slope_max),
        "--surrounding-slope-min",
        str(args.surrounding_slope_min),
        "--min-area-m2",
        str(args.min_area_m2),
        "--max-area-m2",
        str(args.max_area_m2),
        "--ring-pixels",
        str(args.ring_pixels),
        "--tpi-window-pixels",
        str(args.tpi_window_pixels),
        "--max-candidates",
        str(args.max_candidates_per_tile),
    ]
    proc = subprocess.run(cmd, text=True)
    return int(proc.returncode)


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def merge_csv(tile_output_dirs: Sequence[Path], merged_csv: Path) -> int:
    merged_rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []
    for tile_index, tile_dir in enumerate(tile_output_dirs, start=1):
        csv_path = tile_dir / ONE_TILE_CSV
        fields, rows = read_csv_rows(csv_path)
        if fields and not fieldnames:
            fieldnames = ["batch_tile_index", "batch_tile_output_dir"] + fields
        for row in rows:
            out = {"batch_tile_index": str(tile_index), "batch_tile_output_dir": str(tile_dir)}
            out.update(row)
            merged_rows.append(out)

    merged_csv.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = ["batch_tile_index", "batch_tile_output_dir", "candidate_id", "ILAP_SCORE"] + SCORE_COLUMNS
    with merged_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged_rows)
    return len(merged_rows)


def merge_geojson(tile_output_dirs: Sequence[Path], merged_geojson: Path) -> int:
    features: List[Dict[str, object]] = []
    for tile_index, tile_dir in enumerate(tile_output_dirs, start=1):
        path = tile_dir / ONE_TILE_GEOJSON
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            props = feature.setdefault("properties", {})
            props["batch_tile_index"] = tile_index
            props["batch_tile_output_dir"] = str(tile_dir)
            features.append(feature)
    merged_geojson.write_text(json.dumps({
        "type": "FeatureCollection",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "features": features,
    }, indent=2), encoding="utf-8")
    return len(features)


def verify_score_sum(repo_root: Path, merged_csv: Path, report_path: Path) -> int:
    script = repo_root / "tools" / "verify_ilap_score_sum.py"
    cmd = [sys.executable, str(script), "--csv", str(merged_csv), "--output-json", str(report_path)]
    proc = subprocess.run(cmd, text=True)
    return int(proc.returncode)


def write_manifest(path: Path, args: argparse.Namespace, selected: Sequence[Dict[str, object]], tile_results: Sequence[Dict[str, object]], merged_count: int, score_returncode: Optional[int]) -> None:
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tool": "tools/pr_dem_batch_runner.py",
        "profile": args.profile,
        "bbox_wgs84": args.bbox,
        "selected_tile_count": len(selected),
        "processed_tile_count": len(tile_results),
        "merged_candidate_count": merged_count,
        "score_sum_returncode": score_returncode,
        "args": vars(args),
        "tile_results": list(tile_results),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a bounded batch of one-tile DEM pilots and merge outputs.")
    p.add_argument("--geodata-root", default="~/Documents/Data/PR_Geodata")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--output-dir", default="outputs/pr_dem_batch_arecibo_utuado")
    p.add_argument("--profile", choices=sorted(PROFILES), default="arecibo_utuado")
    p.add_argument("--bbox", type=parse_bbox, default=None, help="Optional west,south,east,north bbox in EPSG:4326. Overrides --profile bbox.")
    p.add_argument("--max-tiles", type=int, default=0, help="Optional cap for testing. 0 means all selected tiles.")
    p.add_argument("--dry-run", action="store_true", help="Write selected_tiles.csv and manifest, but do not process DEMs.")
    p.add_argument("--resume", action="store_true", help="Skip tile outputs that already have a one-tile manifest.")
    p.add_argument("--target-resolution-m", type=float, default=5.0)
    p.add_argument("--internal-slope-max", type=float, default=3.0)
    p.add_argument("--surrounding-slope-min", type=float, default=15.0)
    p.add_argument("--min-area-m2", type=float, default=100.0)
    p.add_argument("--max-area-m2", type=float, default=5000.0)
    p.add_argument("--ring-pixels", type=int, default=5)
    p.add_argument("--tpi-window-pixels", type=int, default=21)
    p.add_argument("--max-candidates-per-tile", type=int, default=500)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    geodata_root = Path(args.geodata_root).expanduser().resolve()
    dem_dir = geodata_root / "01_DEM_1m_LiDAR"
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not dem_dir.exists():
        raise SystemExit(f"DEM directory not found: {dem_dir}")
    if not (repo_root / "tools" / "pr_dem_one_tile_pilot.py").exists():
        raise SystemExit(f"Missing one-tile pilot script under repo root: {repo_root}")

    bbox = args.bbox if args.bbox is not None else PROFILES[args.profile]["bbox_wgs84"]
    args.bbox = bbox
    selected = select_tiles(dem_dir, bbox, args.max_tiles)
    write_selected_tiles(selected, output_dir / SELECTED_TILES_CSV)

    if not selected:
        write_manifest(output_dir / BATCH_MANIFEST, args, selected, [], 0, None)
        raise SystemExit("No DEM tiles intersected the selected bbox.")

    tile_results: List[Dict[str, object]] = []
    tile_output_dirs: List[Path] = []

    if not args.dry_run:
        for index, row in enumerate(selected, start=1):
            tile_path = Path(str(row["path"]))
            tile_dir = output_dir / "tiles" / f"{index:03d}_{tile_path.stem}"
            tile_output_dirs.append(tile_dir)
            manifest = tile_dir / ONE_TILE_MANIFEST
            if args.resume and manifest.exists():
                returncode = 0
                skipped = True
            else:
                tile_dir.mkdir(parents=True, exist_ok=True)
                returncode = run_one_tile(repo_root, tile_path, tile_dir, args)
                skipped = False
            tile_results.append({
                "index": index,
                "tile": str(tile_path),
                "output_dir": str(tile_dir),
                "returncode": returncode,
                "skipped_existing": skipped,
            })
            if returncode != 0:
                write_manifest(output_dir / BATCH_MANIFEST, args, selected, tile_results, 0, None)
                raise SystemExit(f"Tile processing failed for {tile_path} with return code {returncode}")

    merged_count = 0
    score_returncode: Optional[int] = None
    if not args.dry_run:
        merged_count = merge_csv(tile_output_dirs, output_dir / MERGED_CSV)
        merge_geojson(tile_output_dirs, output_dir / MERGED_GEOJSON)
        score_returncode = verify_score_sum(repo_root, output_dir / MERGED_CSV, output_dir / SCORE_SUM_REPORT)

    write_manifest(output_dir / BATCH_MANIFEST, args, selected, tile_results, merged_count, score_returncode)

    print(f"Selected tiles: {len(selected)}")
    print(f"Output dir: {output_dir}")
    print(f"Selected tiles CSV: {output_dir / SELECTED_TILES_CSV}")
    if args.dry_run:
        print("Dry run complete: no DEM tiles processed.")
    else:
        print(f"Merged CSV: {output_dir / MERGED_CSV}")
        print(f"Merged GeoJSON: {output_dir / MERGED_GEOJSON}")
        print(f"Score-sum report: {output_dir / SCORE_SUM_REPORT}")
        print(f"Merged candidate rows: {merged_count}")
    return 0 if score_returncode in (None, 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
