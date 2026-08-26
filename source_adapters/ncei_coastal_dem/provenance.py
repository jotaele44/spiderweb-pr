"""Provenance manifests for NCEI Coastal DEM source records."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .registry import DatasetRecord


def utc_now() -> str:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return timestamp.replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_path_for(record: DatasetRecord, cache_root: Path | None) -> Path | None:
    if not cache_root or not record.source_url.endswith(".nc"):
        return None
    return cache_root / f"{record.dataset_id}.nc"


def build_source_manifest(
    records: Iterable[DatasetRecord],
    *,
    accessed_at: str | None = None,
    local_cache_root: Path | str | None = None,
) -> dict[str, object]:
    timestamp = accessed_at or utc_now()
    cache_root = Path(local_cache_root) if local_cache_root else None
    manifest_rows: list[dict[str, object]] = []
    for record in records:
        cache_path = cache_path_for(record, cache_root)
        exists = bool(cache_path and cache_path.exists())
        manifest_rows.append(
            {
                "source_id": f"ncei_coastal_dem:{record.dataset_id}",
                "dataset_id": record.dataset_id,
                "source_family": record.source_family,
                "source_url": record.source_url,
                "accessed_at": timestamp,
                "file_name": str(cache_path) if exists else None,
                "file_size_bytes": cache_path.stat().st_size
                if exists and cache_path
                else None,
                "sha256": sha256_file(cache_path)
                if exists and cache_path
                else None,
                "horizontal_datum": record.horizontal_datum,
                "vertical_datum": record.vertical_datum,
                "resolution_arcsec": record.resolution_arcsec,
                "bbox_wgs84": [],
                "raw_commit_allowed": False,
                "local_cache_path": str(cache_path) if exists else None,
                "derived_outputs": [],
                "confidence": 0.8,
                "review_status": "downloaded_local" if exists else "metadata_only",
                "datum_merge_policy": "same_datum_only",
                "requires_vertical_normalization": False,
                "acquisition_context_refs": [],
            }
        )
    return {
        "adapter": "ncei_coastal_dem",
        "generated_at": timestamp,
        "sources": manifest_rows,
    }


def acquisition_context_leads() -> list[dict[str, object]]:
    notes = (
        "Pasted USAspending query output references PR_USVI_2018_D18 "
        "USGS_LBS_V1.3 under USGS GPSC3. Treat as acquisition context only; "
        "do not claim this award produced any specific NCEI DEM without "
        "source metadata corroboration."
    )
    return [
        {
            "ref_type": "usaspending_award_id",
            "ref_id": "140G0218F0171",
            "confidence": "medium",
            "notes": notes,
        }
    ]
