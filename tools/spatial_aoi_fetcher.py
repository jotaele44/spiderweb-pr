#!/usr/bin/env python3
"""Provider-agnostic AOI -> source-tile planner/fetcher.

The authoritative source-tile index resolves the AOI. The federation Cell_ID
ledger is deliberately downstream: the current canonical PR grid is pixel-space
and has no certified geographic transform, so this module will not fabricate
AOI -> Cell_ID bindings.

v0.1 supports GDAL VRT catalogs such as PRVI_1m_DEM_2018.vrt. A provider may
supply a ``source_url_template`` to enable byte acquisition. Without a URL
binding, planning still works and fetch fails closed with UNRESOLVED_SOURCE_URL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

try:
    import rasterio
    from rasterio.warp import transform_bounds
except Exception:  # pragma: no cover - optional dem extra
    rasterio = None
    transform_bounds = None


@dataclass(frozen=True)
class SourceTile:
    dataset_id: str
    tile_id: str
    source_filename: str
    bbox_native: tuple[float, float, float, float]
    source_crs: str
    width: int
    height: int
    source_url: Optional[str] = None
    expected_size_bytes: Optional[int] = None
    expected_sha256: Optional[str] = None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = tuple(float(x.strip()) for x in value.split(","))
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be west,south,east,north")
    west, south, east, north = parts
    if west >= east or south >= north:
        raise argparse.ArgumentTypeError("bbox must satisfy west < east and south < north")
    return west, south, east, north


def intersects(a: Sequence[float], b: Sequence[float]) -> bool:
    aw, a_s, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and a_s <= bn and an >= bs


def _epsg_from_srs_text(srs_text: str) -> str:
    marker = 'AUTHORITY["EPSG","'
    pos = srs_text.rfind(marker)
    if pos >= 0:
        tail = srs_text[pos + len(marker) :]
        code = tail.split('"', 1)[0]
        if code.isdigit():
            return f"EPSG:{code}"
    return srs_text


def parse_vrt_catalog(
    vrt_path: Path,
    *,
    dataset_id: str,
    source_url_template: Optional[str] = None,
) -> dict[str, Any]:
    root = ET.fromstring(vrt_path.read_bytes())
    x_size = int(root.attrib["rasterXSize"])
    y_size = int(root.attrib["rasterYSize"])
    srs_text = (root.findtext("SRS") or "").strip()
    if not srs_text:
        raise ValueError("VRT has no SRS")
    source_crs = _epsg_from_srs_text(srs_text)

    gt_text = (root.findtext("GeoTransform") or "").strip()
    gt = [float(v.strip()) for v in gt_text.split(",") if v.strip()]
    if len(gt) != 6:
        raise ValueError("VRT GeoTransform must contain six numbers")
    origin_x, pixel_x, rot_x, origin_y, rot_y, pixel_y = gt
    if rot_x != 0 or rot_y != 0:
        raise ValueError("v0.1 VRT catalog parser requires north-up rasters")

    tiles: list[SourceTile] = []
    for source in root.findall(".//ComplexSource"):
        sf = source.find("SourceFilename")
        dst = source.find("DstRect")
        props = source.find("SourceProperties")
        if sf is None or dst is None or props is None or not sf.text:
            continue
        filename = Path(sf.text).name
        xoff = int(dst.attrib["xOff"])
        yoff = int(dst.attrib["yOff"])
        xspan = int(dst.attrib["xSize"])
        yspan = int(dst.attrib["ySize"])
        left = origin_x + xoff * pixel_x
        top = origin_y + yoff * pixel_y
        right = left + xspan * pixel_x
        bottom = top + yspan * pixel_y
        bbox = (
            min(left, right),
            min(bottom, top),
            max(left, right),
            max(bottom, top),
        )
        url = source_url_template.format(filename=filename) if source_url_template else None
        tiles.append(
            SourceTile(
                dataset_id=dataset_id,
                tile_id=filename,
                source_filename=sf.text,
                bbox_native=bbox,
                source_crs=source_crs,
                width=int(props.attrib["RasterXSize"]),
                height=int(props.attrib["RasterYSize"]),
                source_url=url,
            )
        )

    if not tiles:
        raise ValueError("VRT catalog contains no ComplexSource tiles")
    return {
        "dataset_id": dataset_id,
        "catalog_type": "vrt",
        "catalog_path": str(vrt_path),
        "catalog_sha256": sha256_file(vrt_path),
        "raster_size": [x_size, y_size],
        "source_crs": source_crs,
        "geotransform": gt,
        "source_tile_count": len(tiles),
        "tiles": tiles,
    }


def transform_aoi(
    bbox: Sequence[float], source_crs: str, target_crs: str
) -> tuple[float, float, float, float]:
    if source_crs == target_crs:
        return tuple(float(v) for v in bbox)  # type: ignore[return-value]
    if transform_bounds is None:
        raise RuntimeError("rasterio is required to transform AOI CRS")
    out = transform_bounds(source_crs, target_crs, *bbox, densify_pts=21)
    return tuple(float(v) for v in out)


def cache_state(tile: SourceTile, cache_dir: Path) -> dict[str, Any]:
    path = cache_dir / tile.tile_id
    if not path.exists():
        return {
            "status": "ABSENT",
            "path": str(path),
            "sha256": None,
            "size_bytes": None,
        }
    size = path.stat().st_size
    if size <= 0:
        return {
            "status": "INVALID_EMPTY",
            "path": str(path),
            "sha256": None,
            "size_bytes": size,
        }
    digest = sha256_file(path)
    if tile.expected_size_bytes is not None and size != tile.expected_size_bytes:
        return {
            "status": "INVALID_SIZE",
            "path": str(path),
            "sha256": digest,
            "size_bytes": size,
        }
    if tile.expected_sha256 and digest.lower() != tile.expected_sha256.lower():
        return {
            "status": "INVALID_HASH",
            "path": str(path),
            "sha256": digest,
            "size_bytes": size,
        }
    if rasterio is not None:
        try:
            with rasterio.open(path) as src:
                _ = src.width, src.height, src.crs
        except Exception:
            return {
                "status": "INVALID_RASTER",
                "path": str(path),
                "sha256": digest,
                "size_bytes": size,
            }
    status = "LOCAL_HASH_VALID" if tile.expected_sha256 else "LOCAL_VALID_UNPINNED"
    return {
        "status": status,
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
    }


def plan_for_aoi(
    catalog: dict[str, Any],
    *,
    aoi_bbox: Sequence[float],
    aoi_crs: str,
    cache_dir: Path,
) -> dict[str, Any]:
    native_aoi = transform_aoi(aoi_bbox, aoi_crs, catalog["source_crs"])
    selected = [
        tile for tile in catalog["tiles"] if intersects(tile.bbox_native, native_aoi)
    ]
    rows = []
    cached_valid = 0
    unresolved_urls = 0
    expected_bytes = 0
    for tile in selected:
        state = cache_state(tile, cache_dir)
        if state["status"] in {"LOCAL_HASH_VALID", "LOCAL_VALID_UNPINNED"}:
            cached_valid += 1
        if not tile.source_url:
            unresolved_urls += 1
        if state["status"] == "ABSENT" and tile.expected_size_bytes:
            expected_bytes += tile.expected_size_bytes
        rows.append(
            {**asdict(tile), "bbox_native": list(tile.bbox_native), "cache": state}
        )
    return {
        "generated_at_utc": utc_now(),
        "dataset_id": catalog["dataset_id"],
        "aoi_bbox": list(aoi_bbox),
        "aoi_crs": aoi_crs,
        "aoi_bbox_native": list(native_aoi),
        "source_crs": catalog["source_crs"],
        "required_tile_count": len(selected),
        "cached_valid_tile_count": cached_valid,
        "missing_tile_count": len(selected) - cached_valid,
        "unresolved_source_url_count": unresolved_urls,
        "expected_download_bytes_known": expected_bytes,
        "cell_binding_status": "UNAVAILABLE_CANONICAL_GRID_UNGEOREFERENCED",
        "tiles": rows,
    }


def _download_resumable(url: str, destination: Path, timeout: int = 120) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    offset = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "spiderweb-pr/0.1 spatial-aoi-fetcher"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            mode = "ab" if offset and status == 206 else "wb"
            with part.open(mode) as fh:
                shutil.copyfileobj(response, fh, length=1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    os.replace(part, destination)


def fetch_plan(
    plan: dict[str, Any], cache_dir: Path, *, require_complete: bool = True
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures = 0
    for row in plan["tiles"]:
        tile = SourceTile(
            dataset_id=row["dataset_id"],
            tile_id=row["tile_id"],
            source_filename=row["source_filename"],
            bbox_native=tuple(row["bbox_native"]),
            source_crs=row["source_crs"],
            width=int(row["width"]),
            height=int(row["height"]),
            source_url=row.get("source_url"),
            expected_size_bytes=row.get("expected_size_bytes"),
            expected_sha256=row.get("expected_sha256"),
        )
        before = cache_state(tile, cache_dir)
        if before["status"] in {"LOCAL_HASH_VALID", "LOCAL_VALID_UNPINNED"}:
            results.append(
                {"tile_id": tile.tile_id, "action": "REUSE", "state": before}
            )
            continue
        if not tile.source_url:
            failures += 1
            results.append(
                {
                    "tile_id": tile.tile_id,
                    "action": "BLOCKED",
                    "reason": "UNRESOLVED_SOURCE_URL",
                }
            )
            continue
        target = cache_dir / tile.tile_id
        try:
            _download_resumable(tile.source_url, target)
            after = cache_state(tile, cache_dir)
            if after["status"] not in {"LOCAL_HASH_VALID", "LOCAL_VALID_UNPINNED"}:
                raise RuntimeError(after["status"])
            results.append(
                {"tile_id": tile.tile_id, "action": "FETCH", "state": after}
            )
        except Exception as exc:
            failures += 1
            results.append(
                {"tile_id": tile.tile_id, "action": "FAILED", "reason": str(exc)}
            )
    complete = failures == 0
    receipt = {
        "generated_at_utc": utc_now(),
        "dataset_id": plan["dataset_id"],
        "required_tile_count": plan["required_tile_count"],
        "failure_count": failures,
        "complete": complete,
        "require_complete": require_complete,
        "results": results,
    }
    if require_complete and not complete:
        receipt["analysis_gate"] = "BLOCKED_INCOMPLETE_SOURCE_BYTES"
    else:
        receipt["analysis_gate"] = "READY"
    return receipt


def build_task_vrt(tile_paths: Iterable[Path], output_vrt: Path) -> dict[str, Any]:
    paths = [Path(p) for p in tile_paths]
    if not paths:
        raise ValueError("no tile paths supplied")
    exe = shutil.which("gdalbuildvrt")
    if not exe:
        return {
            "status": "BLOCKED_GDALBUILDVRT_UNAVAILABLE",
            "output": str(output_vrt),
        }
    output_vrt.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [exe, str(output_vrt), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {
            "status": "FAILED",
            "returncode": proc.returncode,
            "stderr": proc.stderr,
            "output": str(output_vrt),
        }
    return {
        "status": "READY",
        "output": str(output_vrt),
        "sha256": sha256_file(output_vrt),
    }


def load_provider(path: Path, dataset_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    provider = (payload.get("providers") or {}).get(dataset_id)
    if not isinstance(provider, dict):
        raise SystemExit(f"unknown dataset provider: {dataset_id}")
    return provider


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Plan/fetch source raster tiles for a task AOI."
    )
    p.add_argument("--providers", default="configs/spatial_dataset_providers.json")
    p.add_argument("--dataset", default="PRVI_1m_DEM_2018")
    p.add_argument(
        "--catalog",
        help="Provider catalog path (e.g. PRVI_1m_DEM_2018.vrt); overrides config",
    )
    p.add_argument(
        "--bbox", required=True, type=parse_bbox, help="west,south,east,north"
    )
    p.add_argument("--aoi-crs", default="EPSG:4326")
    p.add_argument("--cache-dir", default="data/cache/spatial")
    p.add_argument("--output-dir", default="outputs/spatial_aoi_fetch")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--allow-partial", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    provider = load_provider(Path(args.providers), args.dataset)
    catalog_value = args.catalog or provider.get("catalog_path")
    if not catalog_value:
        raise SystemExit(
            f"provider {args.dataset} has no bound catalog_path; pass --catalog"
        )
    catalog_path = Path(catalog_value)
    if not catalog_path.exists() or catalog_path.stat().st_size == 0:
        raise SystemExit(f"catalog missing or empty: {catalog_path}")
    cache_dir = Path(args.cache_dir) / args.dataset
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if provider.get("catalog_type") != "vrt":
        raise SystemExit("v0.1 currently supports catalog_type=vrt")
    catalog = parse_vrt_catalog(
        catalog_path,
        dataset_id=args.dataset,
        source_url_template=provider.get("source_url_template"),
    )
    expected_crs = provider.get("catalog_crs_expected")
    if expected_crs and catalog["source_crs"] != expected_crs:
        raise SystemExit(
            f"catalog CRS {catalog['source_crs']} does not match provider contract "
            f"{expected_crs}"
        )
    plan = plan_for_aoi(
        catalog,
        aoi_bbox=args.bbox,
        aoi_crs=args.aoi_crs,
        cache_dir=cache_dir,
    )
    plan_path = output_dir / "acquisition_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in plan.items() if k != "tiles"}, indent=2))
    if not args.fetch:
        return 0
    receipt = fetch_plan(
        plan, cache_dir, require_complete=not args.allow_partial
    )
    receipt_path = output_dir / "acquisition_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(
        json.dumps({k: v for k, v in receipt.items() if k != "results"}, indent=2)
    )
    return 0 if receipt["analysis_gate"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
