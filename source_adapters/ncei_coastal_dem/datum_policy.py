"""Vertical datum guardrails for Coastal DEM metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .registry import DatasetRecord


@dataclass(frozen=True)
class DatumPolicyResult:
    dataset_ids: tuple[str, ...]
    vertical_datums: tuple[str, ...]
    horizontal_datums: tuple[str, ...]
    datum_merge_policy: str
    requires_vertical_normalization: bool
    review_status: str
    notes: str


def evaluate_datum_policy(records: Iterable[DatasetRecord]) -> DatumPolicyResult:
    selected = tuple(records)
    if not selected:
        return DatumPolicyResult(
            (),
            (),
            (),
            "no_datasets",
            False,
            "review_required",
            "no datasets selected",
        )

    missing_vertical = [
        record.dataset_id for record in selected if not record.vertical_datum.strip()
    ]
    if missing_vertical:
        raise ValueError(f"missing vertical datum for: {', '.join(missing_vertical)}")

    vertical_datums = tuple(sorted({record.vertical_datum for record in selected}))
    horizontal_datums = tuple(sorted({record.horizontal_datum for record in selected}))
    dataset_ids = tuple(record.dataset_id for record in selected)

    if len(vertical_datums) == 1:
        return DatumPolicyResult(
            dataset_ids=dataset_ids,
            vertical_datums=vertical_datums,
            horizontal_datums=horizontal_datums,
            datum_merge_policy="same_datum_only",
            requires_vertical_normalization=False,
            review_status="pass",
            notes="selected datasets share one declared vertical datum",
        )

    return DatumPolicyResult(
        dataset_ids=dataset_ids,
        vertical_datums=vertical_datums,
        horizontal_datums=horizontal_datums,
        datum_merge_policy="separate_layers_until_vertical_transform_metadata_exists",
        requires_vertical_normalization=True,
        review_status="review_required",
        notes=(
            "mixed vertical datums require layer separation or explicit vertical "
            "transformation metadata"
        ),
    )
