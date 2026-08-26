"""Registry helpers for NCEI/NOAA Coastal DEM datasets.

The registry is intentionally small and metadata-only. Raw DEM payloads remain
operator-local runtime artifacts and are never committed by this adapter.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_REGISTRY_PATH = Path(
    "data/ncei_coastal_dem/registry/ncei_coastal_dem_priority_datasets.csv"
)
REQUIRED_FIELDS = (
    "dataset_id",
    "source_family",
    "name",
    "area",
    "year",
    "horizontal_datum",
    "vertical_datum",
    "resolution_arcsec",
    "status",
    "source_url",
    "access_method",
    "raw_commit_allowed",
    "priority",
    "notes",
)
VALID_PRIORITIES = {"P0", "P1", "P2"}
FALSE_VALUES = {"false", "0", "no", "n"}


@dataclass(frozen=True)
class DatasetRecord:
    dataset_id: str
    source_family: str
    name: str
    area: str
    year: str
    horizontal_datum: str
    vertical_datum: str
    resolution_arcsec: str
    status: str
    source_url: str
    access_method: str
    raw_commit_allowed: bool
    priority: str
    notes: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "DatasetRecord":
        missing = [
            field for field in REQUIRED_FIELDS if not (row.get(field) or "").strip()
        ]
        if missing:
            raise ValueError(f"missing required registry fields: {', '.join(missing)}")
        raw_commit = row["raw_commit_allowed"].strip().lower()
        if raw_commit not in FALSE_VALUES:
            raise ValueError(
                f"{row['dataset_id']} raw_commit_allowed must be false for DEM payloads"
            )
        priority = row["priority"].strip()
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"{row['dataset_id']} has invalid priority {priority!r}")
        return cls(
            dataset_id=row["dataset_id"].strip(),
            source_family=row["source_family"].strip(),
            name=row["name"].strip(),
            area=row["area"].strip(),
            year=row["year"].strip(),
            horizontal_datum=row["horizontal_datum"].strip(),
            vertical_datum=row["vertical_datum"].strip(),
            resolution_arcsec=row["resolution_arcsec"].strip(),
            status=row["status"].strip(),
            source_url=row["source_url"].strip(),
            access_method=row["access_method"].strip(),
            raw_commit_allowed=False,
            priority=priority,
            notes=row["notes"].strip(),
        )

    def as_manifest_row(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "source_family": self.source_family,
            "name": self.name,
            "area": self.area,
            "year": self.year,
            "horizontal_datum": self.horizontal_datum,
            "vertical_datum": self.vertical_datum,
            "resolution_arcsec": self.resolution_arcsec,
            "status": self.status,
            "source_url": self.source_url,
            "access_method": self.access_method,
            "raw_commit_allowed": self.raw_commit_allowed,
            "priority": self.priority,
            "notes": self.notes,
        }


def load_registry(
    path: Path | str = DEFAULT_REGISTRY_PATH,
) -> tuple[DatasetRecord, ...]:
    registry_path = Path(path)
    with registry_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [
            field for field in REQUIRED_FIELDS if field not in fieldnames
        ]
        if missing_columns:
            joined = ", ".join(missing_columns)
            raise ValueError(f"registry is missing columns: {joined}")
        return tuple(DatasetRecord.from_row(row) for row in reader)


def select_datasets(
    records: Iterable[DatasetRecord],
    *,
    dataset_id: str | None = None,
    priority: str | None = None,
    aoi: str | None = None,
) -> tuple[DatasetRecord, ...]:
    selected = list(records)
    if dataset_id:
        selected = [record for record in selected if record.dataset_id == dataset_id]
    if priority:
        selected = [record for record in selected if record.priority == priority]
    if aoi and aoi.lower() not in {"all", "puerto_rico", "pr"}:
        aoi_l = aoi.lower()
        selected = [
            record
            for record in selected
            if aoi_l in record.area.lower() or aoi_l in record.name.lower()
        ]
    return tuple(selected)


def require_single_dataset(
    records: Iterable[DatasetRecord], dataset_id: str
) -> DatasetRecord:
    matches = [record for record in records if record.dataset_id == dataset_id]
    if not matches:
        raise ValueError(f"unknown dataset id: {dataset_id}")
    if len(matches) > 1:
        raise ValueError(f"registry contains duplicate dataset id: {dataset_id}")
    return matches[0]
