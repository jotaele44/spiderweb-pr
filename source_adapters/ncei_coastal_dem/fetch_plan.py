"""Fetch-plan builder for NCEI Coastal DEM metadata and selected raw payloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .datum_policy import evaluate_datum_policy
from .registry import DatasetRecord, load_registry, select_datasets

DEFAULT_OUTPUT_ROOT = Path("outputs/ncei_coastal_dem")
DEFAULT_CACHE_DIR = Path("data/ncei_coastal_dem/cache")
RAW_SUFFIXES = (".nc", ".tif", ".tiff", ".zip")


@dataclass(frozen=True)
class FetchTask:
    dataset_id: str
    source_url: str
    access_method: str
    local_cache_path: str | None
    metadata_only: bool
    raw_commit_allowed: bool
    review_status: str
    notes: str

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "source_url": self.source_url,
            "access_method": self.access_method,
            "local_cache_path": self.local_cache_path,
            "metadata_only": self.metadata_only,
            "raw_commit_allowed": self.raw_commit_allowed,
            "review_status": self.review_status,
            "notes": self.notes,
        }


def cache_name_for(record: DatasetRecord) -> str:
    suffix = ".nc" if record.source_url.endswith(".nc") else ".source"
    return f"{record.dataset_id}{suffix}"


def build_fetch_plan(
    records: tuple[DatasetRecord, ...] | None = None,
    *,
    aoi: str = "puerto_rico",
    dataset_id: str | None = None,
    priority: str | None = None,
    metadata_only: bool = True,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> dict[str, object]:
    registry_records = records if records is not None else load_registry()
    selected = select_datasets(
        registry_records,
        dataset_id=dataset_id,
        priority=priority,
        aoi=aoi,
    )
    datum_result = evaluate_datum_policy(selected)
    cache_root = Path(cache_dir)
    tasks = tuple(
        FetchTask(
            dataset_id=record.dataset_id,
            source_url=record.source_url,
            access_method=record.access_method,
            local_cache_path=None
            if metadata_only
            else str(cache_root / cache_name_for(record)),
            metadata_only=metadata_only,
            raw_commit_allowed=False,
            review_status="planned_metadata_only"
            if metadata_only
            else "planned_raw_cache_fetch",
            notes=record.notes,
        )
        for record in selected
    )
    return {
        "adapter": "ncei_coastal_dem",
        "aoi": aoi,
        "metadata_only": metadata_only,
        "selected_count": len(selected),
        "tasks": [task.as_dict() for task in tasks],
        "datum_policy": {
            "dataset_ids": datum_result.dataset_ids,
            "vertical_datums": datum_result.vertical_datums,
            "horizontal_datums": datum_result.horizontal_datums,
            "datum_merge_policy": datum_result.datum_merge_policy,
            "requires_vertical_normalization": (
                datum_result.requires_vertical_normalization
            ),
            "review_status": datum_result.review_status,
            "notes": datum_result.notes,
        },
    }
