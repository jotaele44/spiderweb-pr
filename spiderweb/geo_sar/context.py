"""Read-only, bounded pilot ledger queries; no acquisition or coverage promotion."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "registry/geo_sar/pilot_001_asset_ledger.json"


def validate_bbox(bounds):
    if len(bounds) != 4 or any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in bounds
    ):
        raise ValueError("bbox requires four finite numbers")
    w, s, e, n = bounds
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90 and e - w <= 180):
        raise ValueError("invalid or unsupported bbox")
    return tuple(bounds)


def resolve_context(bounds, ledger_path=LEDGER):
    from rasterio.warp import transform_geom

    bounds = validate_bbox(bounds)
    raw = ledger_path.read_bytes()
    ledger = json.loads(raw)
    revision = hashlib.sha256(raw).hexdigest()
    area = box(*bounds)
    pilot = box(*ledger["pilot_extent"]["bbox_wgs84"])
    options = {}
    unresolved = []
    touches = []
    for asset in ledger["assets"]:
        verified = asset.get("verified") or {}
        native = verified.get("native_footprint")
        crs = verified.get("native_crs")
        if (
            not native
            or not crs
            or verified.get("verification_status") != "HEADER_VERIFIED"
        ):
            unresolved.append(asset["asset_id"])
            continue
        native_box = box(*native).segmentize(max(native[2] - native[0], 1e-9) / 64)
        footprint = shape(
            transform_geom(crs, "EPSG:4326", native_box.__geo_interface__)
        )
        intersection = area.intersection(footprint)
        if intersection.is_empty:
            continue
        if intersection.area == 0:
            touches.append(asset["asset_id"])
            continue
        key = asset["dataset_version_id"]
        option = options.setdefault(
            key,
            {
                "dataset_version_id": key,
                "dataset_id": asset["dataset_id"],
                "source_id": asset["source_id"],
                "assets": [],
                "valid_data_coverage": "UNVERIFIED",
            },
        )
        if (
            option["dataset_id"] != asset["dataset_id"]
            or option["source_id"] != asset["source_id"]
        ):
            raise ValueError("conflicting dataset version identity")
        option["assets"].append(
            {
                "asset_id": asset["asset_id"],
                "filename": asset["native_identity"]["original_filename"],
                "acquisition_status": asset["availability"]["acquisition_status"],
                "integrity_status": asset["integrity"]["verification_status"],
                "expected_size_bytes": asset["integrity"]["expected_size_bytes"],
                "licensing_status": asset["availability"]["licensing_status"],
                "footprint": list(footprint.bounds),
            }
        )
    return {
        "context_id": hashlib.sha256(
            json.dumps([bounds, revision]).encode()
        ).hexdigest(),
        "bbox": bounds,
        "catalog_revision": revision,
        "catalog_scope": "PILOT_ONLY",
        "extent_within_pilot": pilot.covers(area),
        "catalog_assets_examined": len(ledger["assets"]),
        "options": sorted(options.values(), key=lambda x: x["dataset_version_id"]),
        "unresolved_asset_ids": unresolved,
        "touch_only_asset_ids": touches,
        "segment_binding": "UNVERIFIED",
    }
