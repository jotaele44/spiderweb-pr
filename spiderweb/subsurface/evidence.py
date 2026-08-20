"""Evidence and spatial-state adjudication for subsurface relevance."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum
import math
from typing import Iterable

from shapely.geometry.base import BaseGeometry


class EvidenceTier(IntEnum):
    UNRESOLVED = 0
    CANDIDATE = 1
    SUPPORTING = 2
    DIRECT = 3
    CONTRADICTED = 4


class SpatialState(StrEnum):
    FULLY_WITHIN = "FULLY_WITHIN"
    PARTIAL = "PARTIAL"
    TOUCH_ONLY = "TOUCH_ONLY"
    OUTSIDE = "OUTSIDE"
    NULL_EMPTY = "NULL_EMPTY"
    UNRESOLVED = "UNRESOLVED"


class CertificationState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"
    PROVISIONAL = "PROVISIONAL"
    CANDIDATE_NOT_IDENTITY = "CANDIDATE_NOT_IDENTITY"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    source_id: str
    layer_family: str
    source_uri: str
    source_sha256: str | None
    retrieved_utc: str | None
    evidence_tier: EvidenceTier
    basis: tuple[str, ...]
    spatial_state: SpatialState
    distance_to_aoi: float | None
    geometry_wkt: str | None
    attributes: dict
    certification: CertificationState
    score: float | None = None
    tied_top_score: bool = False


def spatial_state(aoi: BaseGeometry, feature: BaseGeometry | None) -> SpatialState:
    if feature is None or feature.is_empty:
        return SpatialState.NULL_EMPTY
    if not feature.is_valid:
        return SpatialState.UNRESOLVED
    if aoi.contains(feature) or aoi.equals(feature):
        return SpatialState.FULLY_WITHIN
    if aoi.touches(feature) and not aoi.interiors[0].intersects(feature):
        return SpatialState.TOUCH_ONLY
    if aoi.intersects(feature):
        return SpatialState.PARTIAL
    return SpatialState.OUTSIDE


def _distance(aoi: BaseGeometry, feature: BaseGeometry | None) -> float | None:
    if feature is None or feature.is_empty or not feature.is_valid:
        return None
    value = float(aoi.distance(feature))
    return value if math.isfinite(value) else None


def adjudicate_feature(
    *,
    aoi: BaseGeometry,
    record_id: str,
    source_id: str,
    layer_family: str,
    source_uri: str,
    feature: BaseGeometry | None,
    asserted_tier: EvidenceTier,
    basis: Iterable[str],
    attributes: dict | None = None,
    source_sha256: str | None = None,
    retrieved_utc: str | None = None,
    score: float | None = None,
) -> EvidenceRecord:
    """Classify one feature while enforcing non-promotion safeguards.

    `proximity_only`, `nearest_only`, and `name_only` are discovery bases and can
    never yield SUPPORTING or DIRECT. Invalid geometry is UNRESOLVED. This function
    deliberately does not infer identity, intent, connectivity, or underground use.
    """

    bases = tuple(sorted(set(str(v).lower() for v in basis)))
    state = spatial_state(aoi, feature)
    tier = asserted_tier
    heuristic_only = {
        "proximity_only",
        "nearest_only",
        "name_only",
        "normalized_name_only",
        "same_category",
        "source_absence",
    }
    if set(bases) & heuristic_only and tier > EvidenceTier.CANDIDATE:
        tier = EvidenceTier.CANDIDATE
    if state in {SpatialState.NULL_EMPTY, SpatialState.UNRESOLVED}:
        tier = EvidenceTier.UNRESOLVED

    certification = (
        CertificationState.CANDIDATE_NOT_IDENTITY
        if tier == EvidenceTier.CANDIDATE
        else CertificationState.UNRESOLVED
        if tier == EvidenceTier.UNRESOLVED
        else CertificationState.PROVISIONAL
    )
    return EvidenceRecord(
        record_id=record_id,
        source_id=source_id,
        layer_family=layer_family,
        source_uri=source_uri,
        source_sha256=source_sha256,
        retrieved_utc=retrieved_utc,
        evidence_tier=tier,
        basis=bases,
        spatial_state=state,
        distance_to_aoi=_distance(aoi, feature),
        geometry_wkt=None if feature is None else feature.wkt,
        attributes=dict(attributes or {}),
        certification=certification,
        score=score,
    )


def mark_top_score_ties(records: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
    records = list(records)
    scored = [r for r in records if r.score is not None and math.isfinite(r.score)]
    if not scored:
        return records
    top = max(r.score for r in scored if r.score is not None)
    top_ids = {r.record_id for r in scored if r.score == top}
    tied = len(top_ids) > 1
    return [replace(r, tied_top_score=(tied and r.record_id in top_ids)) for r in records]


def validate_records(records: Iterable[EvidenceRecord]) -> dict[str, int]:
    records = list(records)
    ids = [r.record_id for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evidence record_id")
    for record in records:
        if not record.source_id:
            raise ValueError("source_id is required")
        if not record.layer_family:
            raise ValueError("layer_family is required")
        if record.score is not None and not math.isfinite(record.score):
            raise ValueError("score must be finite or null")
    return {
        "records": len(records),
        "direct": sum(r.evidence_tier == EvidenceTier.DIRECT for r in records),
        "supporting": sum(r.evidence_tier == EvidenceTier.SUPPORTING for r in records),
        "candidate": sum(r.evidence_tier == EvidenceTier.CANDIDATE for r in records),
        "contradicted": sum(r.evidence_tier == EvidenceTier.CONTRADICTED for r in records),
        "unresolved": sum(r.evidence_tier == EvidenceTier.UNRESOLVED for r in records),
    }
