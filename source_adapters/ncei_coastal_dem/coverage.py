"""Coverage ledger generation for NCEI Coastal DEM metadata."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .registry import DatasetRecord

LIVE_STATUSES = {"live_thredds", "live_cudem_access", "available_live"}
PLANNED_STATUSES = {"planned_pdf_only", "planned"}


def coverage_status(record: DatasetRecord) -> str:
    status = record.status.strip().lower()
    if status in LIVE_STATUSES or status.startswith("live_"):
        return "available_live"
    if status in PLANNED_STATUSES:
        return "planned_pdf_only"
    if "catalog" in status:
        return "cataloged_only"
    return "review_required"


def build_coverage_report(
    records: Iterable[DatasetRecord], *, aoi: str = "puerto_rico"
) -> dict[str, object]:
    selected = tuple(records)
    statuses = [coverage_status(record) for record in selected]
    counts = Counter(statuses)
    live_count = counts.get("available_live", 0)
    live_pct = round((live_count / len(selected)) * 100, 2) if selected else 0.0
    return {
        "adapter": "ncei_coastal_dem",
        "aoi": aoi,
        "expected_datasets": len(selected),
        "status_counts": dict(sorted(counts.items())),
        "coverage_pct_available_live": live_pct,
        "datasets": [
            {
                "dataset_id": record.dataset_id,
                "area": record.area,
                "priority": record.priority,
                "coverage_status": coverage_status(record),
                "vertical_datum": record.vertical_datum,
                "resolution_arcsec": record.resolution_arcsec,
                "source_url": record.source_url,
            }
            for record in selected
        ],
    }
