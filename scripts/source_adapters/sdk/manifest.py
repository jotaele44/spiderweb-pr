"""Manifest and coverage-ledger helpers for source adapters."""

from __future__ import annotations

import csv
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .core import CoverageSummary, DownloadResult


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ManifestEngine:
    """Write small reproducibility artifacts for source-adapter runs."""

    def __init__(self, manifest_root: Path) -> None:
        self.manifest_root = Path(manifest_root)

    def write_csv(self, relative_path: str, rows: Iterable[Mapping[str, object]], fieldnames: Sequence[str]) -> Path:
        path = self.manifest_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_source_manifest(self, source_row: Mapping[str, object]) -> Path:
        row = dict(source_row)
        row.setdefault("manifest_timestamp_utc", utc_now())
        return self.write_csv("source_manifest.csv", [row], list(row.keys()))

    def write_expected_universe(self, rows: Iterable[Mapping[str, object]], filename: str = "expected_universe.csv") -> Path:
        materialized = [dict(row) for row in rows]
        if not materialized:
            return self.write_csv(filename, [], ["id"])
        fieldnames = list(dict.fromkeys(key for row in materialized for key in row.keys()))
        return self.write_csv(filename, materialized, fieldnames)

    def write_download_ledger(self, records: Sequence[DownloadResult], filename: str = "download_ledger.csv") -> Path:
        rows = [_row(record) for record in records]
        fields = list(DownloadResult.__dataclass_fields__.keys())
        return self.write_csv(filename, rows, fields)

    def write_sha256_manifest(self, records: Sequence[DownloadResult], filename: str = "sha256_manifest.csv") -> Path:
        return self.write_csv(
            filename,
            [
                {
                    "request_id": record.request_id,
                    "filename": record.filename,
                    "sha256": record.sha256,
                    "bytes": record.bytes,
                    "review_status": record.review_status,
                }
                for record in records
            ],
            ["request_id", "filename", "sha256", "bytes", "review_status"],
        )

    def write_coverage_ledger(self, summary: CoverageSummary, filename: str = "coverage_ledger.csv") -> Path:
        row = {
            "expected": summary.expected,
            "requested": summary.requested,
            "acquired": summary.acquired,
            "failed": summary.failed,
            "hold": summary.hold,
            "skipped": summary.skipped,
            "unresolved": summary.unresolved,
            "coverage_pct": summary.coverage_pct,
            "generated_timestamp_utc": utc_now(),
        }
        return self.write_csv(filename, [row], list(row.keys()))



def summarize_coverage(expected: int, requested: int, records: Sequence[DownloadResult]) -> CoverageSummary:
    acquired = sum(1 for record in records if record.review_status in {"raw", "validated", "promoted"})
    failed = sum(1 for record in records if record.review_status == "failed")
    hold = sum(1 for record in records if record.review_status == "hold")
    return CoverageSummary(
        expected=expected,
        requested=requested,
        acquired=acquired,
        failed=failed,
        hold=hold,
        unresolved=failed + hold,
    )


def _row(value: object) -> dict[str, object]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"cannot serialize row of type {type(value)!r}")
