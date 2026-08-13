from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .cli import FetchFailure, fetch_with_receipt
from .core import SOURCE_SPECS, geojson_feature_rows, nhd_query_params, nid_query_params, sciencebase_file_url, schema_fingerprint, sha256_bytes
from .step5b_transaction import nhd_page_set_manifest, write_individual_receipt


def _receipt_dir(manifest_root: Path, run_id: str) -> Path:
    return manifest_root / "live_receipts" / run_id / "receipts"


def _freeze_receipt(manifest_root: Path, run_id: str, fetched: Any) -> dict[str, Any]:
    write_individual_receipt(_receipt_dir(manifest_root, run_id), fetched.receipt)
    return asdict(fetched.receipt)


def _require_ok(fetched: Any) -> None:
    if fetched.receipt.transport_state != "OK":
        raise FetchFailure(fetched.receipt)


def stage_tiger(*, raw_root: Path, manifest_root: Path, run_id: str) -> dict[str, Any]:
    spec = SOURCE_SPECS["TIGER_PR_BOUNDARY"]
    fetched = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, expected_content="zip", raw_root=raw_root, raw_name="tl_2025_us_state.zip")
    receipt = _freeze_receipt(manifest_root, run_id, fetched)
    _require_ok(fetched)
    with zipfile.ZipFile(io.BytesIO(fetched.payload)) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"UNEXPECTED_MEDIA: corrupt TIGER member {bad}")
        members = sorted(archive.namelist())
    return {"source": "tiger", "source_id": spec.source_id, "receipts": [receipt], "raw_role": "RAW_REMOTE_ZIP", "raw_path": fetched.receipt.raw_path, "raw_sha256": fetched.receipt.raw_bytes_sha256, "schema_fingerprint": sha256_bytes(json.dumps(members, separators=(",", ":")).encode()), "media_valid": True, "promotion_performed": False}


def stage_nhd(*, raw_root: Path, manifest_root: Path, run_id: str) -> dict[str, Any]:
    spec = SOURCE_SPECS["USGS_NHD_WATERBODY"]
    receipt_objects = []
    pages = []
    rows = []
    offset = 0
    while True:
        params = nhd_query_params(offset=offset)
        fetched = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, params=params, expected_content="geojson", raw_root=raw_root, raw_name=f"nhd_page_{offset:06d}.geojson", page_offset=offset)
        _freeze_receipt(manifest_root, run_id, fetched)
        receipt_objects.append(fetched.receipt)
        _require_ok(fetched)
        page = json.loads(fetched.payload.decode("utf-8"))
        features = page.get("features")
        if not isinstance(features, list):
            raise RuntimeError(f"SCHEMA_CHANGED: NHD page offset={offset} features is not a list")
        pages.append(features)
        for feature in features:
            row = dict(feature.get("properties") or {})
            row["__geometry__"] = feature.get("geometry")
            rows.append(row)
        if len(features) < 2000:
            break
        next_offset = offset + len(features)
        if next_offset <= offset:
            raise RuntimeError("SCHEMA_CHANGED: NHD pagination did not advance")
        offset = next_offset
    page_set = nhd_page_set_manifest(receipt_objects)
    return {"source": "nhd", "source_id": spec.source_id, "receipts": [asdict(r) for r in receipt_objects], "raw_role": "RAW_PAGE_SET", "raw_page_set": page_set, "page_features": pages, "schema_fingerprint": schema_fingerprint(rows), "promotion_performed": False}


def stage_nid(*, raw_root: Path, manifest_root: Path, run_id: str) -> dict[str, Any]:
    spec = SOURCE_SPECS["USACE_NID_DAMS"]
    params = nid_query_params()
    fetched = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, params=params, expected_content="geojson", raw_root=raw_root, raw_name="nid_pr.geojson")
    receipt = _freeze_receipt(manifest_root, run_id, fetched)
    _require_ok(fetched)
    data = json.loads(fetched.payload.decode("utf-8"))
    if not isinstance(data.get("features"), list):
        raise RuntimeError("SCHEMA_CHANGED: NID GeoJSON features is absent or not a list")
    rows = geojson_feature_rows(fetched.payload)
    return {"source": "nid", "source_id": spec.source_id, "receipts": [receipt], "raw_role": "RAW_REMOTE_GEOJSON", "raw_path": fetched.receipt.raw_path, "raw_sha256": fetched.receipt.raw_bytes_sha256, "schema_fingerprint": schema_fingerprint(rows), "promotion_performed": False}


def stage_bathy(*, raw_root: Path, manifest_root: Path, run_id: str) -> dict[str, Any]:
    spec = SOURCE_SPECS["USGS_INLAND_BATHY_V4"]
    metadata = fetch_with_receipt(source_id=spec.source_id, url=spec.endpoint, expected_content="sciencebase-item-json", raw_root=raw_root, raw_name="sciencebase_item.json", relation="SCIENCEBASE_ITEM_METADATA")
    metadata_receipt = _freeze_receipt(manifest_root, run_id, metadata)
    _require_ok(metadata)
    item = json.loads(metadata.payload.decode("utf-8"))
    file_url = sciencebase_file_url(item)
    archive = fetch_with_receipt(source_id=spec.source_id, url=file_url, expected_content="zip", raw_root=raw_root, raw_name="USGS_InlandBathyResearch_Invent_v4.gdb.zip", parent_receipt_id=metadata.receipt.receipt_id, relation="RESOLVED_CANONICAL_FILE_FROM_METADATA")
    archive_receipt = _freeze_receipt(manifest_root, run_id, archive)
    _require_ok(archive)
    with zipfile.ZipFile(io.BytesIO(archive.payload)) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"UNEXPECTED_MEDIA: corrupt Inland Bathymetry member {bad}")
        members = sorted(zf.namelist())
    return {"source": "inland-bathy", "source_id": spec.source_id, "receipts": [metadata_receipt, archive_receipt], "raw_role": "RAW_METADATA_PLUS_REMOTE_ZIP", "metadata_raw_path": metadata.receipt.raw_path, "archive_raw_path": archive.receipt.raw_path, "archive_raw_sha256": archive.receipt.raw_bytes_sha256, "metadata_file_receipt_binding": archive.receipt.parent_receipt_id == metadata.receipt.receipt_id, "schema_fingerprint": sha256_bytes(json.dumps(members, separators=(",", ":")).encode()), "promotion_performed": False}


STAGED_PULLERS = {"tiger": stage_tiger, "nhd": stage_nhd, "nid": stage_nid, "inland-bathy": stage_bathy}
