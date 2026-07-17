#!/usr/bin/env python3
"""Validate NOAA/NCEI coastal DEM source manifests and optional OPeNDAP rasters.

Default mode is source-first and metadata-only. It does not download or commit
NetCDF/GeoTIFF raster products. Runtime QA reports should be written to ignored
paths such as outputs/.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class ValidationError(RuntimeError):
    """Raised when source validation fails."""


def load_manifest(path: Path) -> Dict[str, Any]:
    """Load JSON-compatible YAML, with optional PyYAML fallback."""

    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as json_error:
        try:
            import yaml  # type: ignore
        except ImportError as import_error:
            raise ValidationError(
                f"{path} is not JSON-compatible YAML and PyYAML is not installed"
            ) from import_error
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValidationError(f"Manifest root must be an object: {path}")
        return loaded


def require_keys(obj: Dict[str, Any], keys: Iterable[str], context: str) -> None:
    missing = [key for key in keys if key not in obj]
    if missing:
        raise ValidationError(f"{context} missing required keys: {', '.join(missing)}")


def find_dataset(manifest: Dict[str, Any], dataset_key: str) -> Dict[str, Any]:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        raise ValidationError("manifest.datasets must be a list")
    for dataset in datasets:
        if isinstance(dataset, dict) and dataset.get("dataset_key") == dataset_key:
            return dataset
    raise ValidationError(f"dataset_key not found: {dataset_key}")


def validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    """Dependency-free structural validation for CI/source hygiene."""

    warnings: List[str] = []
    require_keys(
        manifest,
        ["manifest_version", "source_family", "evidence_tier", "repo_policy", "datasets"],
        "manifest",
    )
    if manifest["evidence_tier"] not in {"T1", "T2", "T3", "T4"}:
        raise ValidationError("manifest.evidence_tier must be one of T1/T2/T3/T4")

    repo_policy = manifest["repo_policy"]
    if not isinstance(repo_policy, dict):
        raise ValidationError("manifest.repo_policy must be an object")
    require_keys(repo_policy, ["commit_policy", "do_not_commit"], "repo_policy")

    blocked = set(repo_policy.get("do_not_commit", []))
    for pattern in {"*.nc", "*.tif", "*.tiff", "tile_cache/", "cache/", "outputs/"}:
        if pattern not in blocked:
            warnings.append(f"repo_policy.do_not_commit does not include {pattern}")

    datasets = manifest["datasets"]
    if not isinstance(datasets, list) or not datasets:
        raise ValidationError("manifest.datasets must be a non-empty list")

    seen: set[str] = set()
    for idx, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            raise ValidationError(f"datasets[{idx}] must be an object")
        require_keys(
            dataset,
            [
                "dataset_key",
                "name",
                "year",
                "status_in_snapshot",
                "vertical_datum",
                "horizontal_datum",
                "spatial_resolution",
                "validation",
            ],
            f"datasets[{idx}]",
        )
        key = dataset["dataset_key"]
        if key in seen:
            raise ValidationError(f"duplicate dataset_key: {key}")
        seen.add(key)

        validation = dataset["validation"]
        if not isinstance(validation, dict) or "promotion_status" not in validation:
            raise ValidationError(f"{key}.validation.promotion_status is required")

        url = dataset.get("opendap_url")
        if url is not None and not str(url).startswith("https://"):
            raise ValidationError(f"{key}.opendap_url must be https")

        bounds = dataset.get("bounds_wgs84")
        if bounds is not None:
            require_keys(bounds, ["min_lat", "max_lat", "min_lon", "max_lon"], f"{key}.bounds_wgs84")
            if not bounds["min_lat"] < bounds["max_lat"]:
                raise ValidationError(f"{key}.bounds_wgs84 lat bounds are invalid")
            if not bounds["min_lon"] < bounds["max_lon"]:
                raise ValidationError(f"{key}.bounds_wgs84 lon bounds are invalid")

        grid_shape = dataset.get("grid_shape")
        if grid_shape is not None:
            require_keys(grid_shape, ["lat", "lon"], f"{key}.grid_shape")
            if int(grid_shape["lat"]) <= 0 or int(grid_shape["lon"]) <= 0:
                raise ValidationError(f"{key}.grid_shape dimensions must be positive")

    return warnings


def fetch_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "spiderweb-pr-source-validator/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_dds(dds_text: str, elevation_var: str = "Band1") -> Dict[str, Any]:
    """Parse a THREDDS ``.dds`` response. The elevation grid variable name varies
    across NCEI DEM vintages (``Band1`` on the GDAL-exported rasters, ``z`` on the
    1/3-arc-second MHW DEMs), so it is a parameter rather than hardcoded."""

    lat_match = re.search(r"Float64\s+lat\[lat\s*=\s*(\d+)\]", dds_text)
    lon_match = re.search(r"Float64\s+lon\[lon\s*=\s*(\d+)\]", dds_text)
    var_match = re.search(
        rf"Float32\s+{re.escape(elevation_var)}\[lat\s*=\s*(\d+)\]\[lon\s*=\s*(\d+)\]", dds_text
    )
    return {
        "lat_dim": int(lat_match.group(1)) if lat_match else None,
        "lon_dim": int(lon_match.group(1)) if lon_match else None,
        "elevation_var": elevation_var,
        "var_shape": [int(var_match.group(1)), int(var_match.group(2))] if var_match else None,
        "has_crs_string": "String crs" in dds_text,
        "has_var": elevation_var in dds_text,
    }


def parse_actual_range_from_das(das_text: str, variable: str) -> Optional[List[float]]:
    match = re.search(rf"{re.escape(variable)}\s*\{{.*?actual_range\s+([^;]+);", das_text, flags=re.DOTALL)
    if not match:
        return None
    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", match.group(1))
    if len(numbers) >= 2:
        return [float(numbers[0]), float(numbers[1])]
    return None


def validate_live_metadata(dataset: Dict[str, Any]) -> Dict[str, Any]:
    url = dataset.get("opendap_url")
    if not url:
        raise ValidationError(f"{dataset.get('dataset_key')} has no opendap_url")

    elevation_var = dataset.get("elevation_var", "Band1")
    dds_text = fetch_text(f"{url}.dds")
    parsed_dds = parse_dds(dds_text, elevation_var)
    expected = dataset.get("grid_shape", {})
    if expected.get("lat") and parsed_dds["lat_dim"] != int(expected["lat"]):
        raise ValidationError(f"DDS lat mismatch: expected {expected['lat']}, got {parsed_dds['lat_dim']}")
    if expected.get("lon") and parsed_dds["lon_dim"] != int(expected["lon"]):
        raise ValidationError(f"DDS lon mismatch: expected {expected['lon']}, got {parsed_dds['lon_dim']}")

    report: Dict[str, Any] = {
        "opendap_url": url,
        "dds_url": f"{url}.dds",
        "das_url": f"{url}.das",
        "elevation_var": elevation_var,
        "dds_status": "ok",
        "dds": parsed_dds,
        "das_status": "pending",
    }
    try:
        das_text = fetch_text(f"{url}.das")
        report["das_status"] = "ok"
        report["elevation_actual_range_from_das"] = parse_actual_range_from_das(das_text, elevation_var)
    except Exception as error:  # live metadata can fail without invalidating local manifest
        report["das_status"] = f"unavailable: {error}"
    return report


def sample_raster(dataset: Dict[str, Any], stride: int) -> Dict[str, Any]:
    try:
        import numpy as np  # type: ignore
        import xarray as xr  # type: ignore
    except ImportError as error:
        raise ValidationError("--sample-raster requires xarray and numpy") from error

    url = dataset.get("opendap_url")
    if not url:
        raise ValidationError(f"{dataset.get('dataset_key')} has no opendap_url")
    if stride < 1:
        raise ValidationError("--stride must be >= 1")

    elevation_var = dataset.get("elevation_var", "Band1")
    ds = xr.open_dataset(url)
    if elevation_var not in ds:
        raise ValidationError(f"{elevation_var} not present in dataset")
    values = ds[elevation_var].isel(lat=slice(None, None, stride), lon=slice(None, None, stride)).load().values
    finite = np.isfinite(values)
    total = int(values.size)
    finite_count = int(finite.sum())
    min_value = float(np.nanmin(values)) if finite_count else math.nan
    max_value = float(np.nanmax(values)) if finite_count else math.nan
    nodata_percent = 100.0 * (1.0 - finite_count / total) if total else math.nan
    return {
        "sample_stride": stride,
        "sample_shape": list(values.shape),
        "sample_total_cells": total,
        "sample_finite_cells": finite_count,
        "sample_nodata_percent": nodata_percent,
        "sample_min": min_value,
        "sample_max": max_value,
        "sample_flat_zero_flag": bool(finite_count and min_value == 0.0 and max_value == 0.0),
    }


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    warnings = validate_manifest(manifest)
    dataset = find_dataset(manifest, args.dataset)
    report: Dict[str, Any] = {
        "script": "scripts/acquire/noaa_ncei_opendap.py",
        "manifest": str(manifest_path),
        "dataset_key": args.dataset,
        "metadata_only": args.metadata_only,
        "validate_live": args.validate_live,
        "sample_raster": args.sample_raster,
        "manifest_validation": {"status": "ok", "warnings": warnings},
        "dataset_validation": {
            "dataset_key": dataset["dataset_key"],
            "name": dataset["name"],
            "year": dataset["year"],
            "vertical_datum": dataset["vertical_datum"],
            "horizontal_datum": dataset["horizontal_datum"],
            "spatial_resolution": dataset["spatial_resolution"],
            "promotion_status": dataset.get("validation", {}).get("promotion_status"),
        },
    }
    if args.validate_live:
        report["live_metadata"] = validate_live_metadata(dataset)
    if args.sample_raster:
        report["raster_sample"] = sample_raster(dataset, args.stride)
    return report


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data_sources/noaa/ncei_coastal_dems.yml")
    parser.add_argument("--dataset", default="san_juan_19_prvd02_2015")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--validate-live", action="store_true")
    parser.add_argument("--sample-raster", action="store_true")
    parser.add_argument("--stride", type=int, default=50)
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.metadata_only and (args.validate_live or args.sample_raster):
        raise ValidationError("--metadata-only cannot be combined with --validate-live or --sample-raster")
    if not args.metadata_only and not args.validate_live and not args.sample_raster:
        args.metadata_only = True
    report = build_report(args)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
