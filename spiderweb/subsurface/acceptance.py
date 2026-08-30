"""Acceptance snapshots and non-regression gates for AOI adapter evolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .dispatcher import DispatchTask
from .evidence import EvidenceRecord, validate_records


@dataclass(frozen=True)
class AcceptanceDiff:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]


def _record_key(family: str, record: EvidenceRecord) -> str:
    return f"{family}|{record.source_id}|{record.record_id}"


def _record_fingerprint(record: EvidenceRecord) -> str:
    payload = {
        "record_id": record.record_id,
        "source_id": record.source_id,
        "layer_family": record.layer_family,
        "source_uri": record.source_uri,
        "source_sha256": record.source_sha256,
        "evidence_tier": record.evidence_tier.name,
        "basis": list(record.basis),
        "spatial_state": record.spatial_state.value,
        "distance_to_aoi": record.distance_to_aoi,
        "geometry_wkt": record.geometry_wkt,
        "attributes": record.attributes,
        "certification": record.certification.value,
        "score": record.score,
        "tied_top_score": record.tied_top_score,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_acceptance_snapshot(
    *,
    aoi_canonical_sha256: str,
    dispatch_plan: Iterable[DispatchTask],
    records_by_family: dict[str, list[EvidenceRecord]],
) -> dict:
    """Build a deterministic, source-preserving acceptance snapshot."""

    flattened: list[EvidenceRecord] = []
    for records in records_by_family.values():
        flattened.extend(records)
    validate_records(flattened)

    records = {}
    sources: dict[str, dict] = {}
    for family in sorted(records_by_family):
        for record in sorted(
            records_by_family[family], key=lambda r: (r.source_id, r.record_id)
        ):
            key = _record_key(family, record)
            records[key] = {
                "fingerprint": _record_fingerprint(record),
                "family": family,
                "source_id": record.source_id,
                "record_id": record.record_id,
                "evidence_tier": record.evidence_tier.name,
                "spatial_state": record.spatial_state.value,
            }
            source_key = f"{family}|{record.source_id}"
            source = sources.setdefault(
                source_key,
                {
                    "family": family,
                    "source_id": record.source_id,
                    "source_uri": record.source_uri,
                    "source_sha256": record.source_sha256,
                    "record_ids": [],
                },
            )
            source["record_ids"].append(record.record_id)

    for source in sources.values():
        source["record_ids"] = sorted(source["record_ids"])
        source["record_count"] = len(source["record_ids"])

    plan = [asdict(task) for task in dispatch_plan]
    return {
        "schema": "spiderweb.subsurface.acceptance.v1",
        "aoi_canonical_sha256": aoi_canonical_sha256,
        "dispatch_plan": sorted(plan, key=lambda x: x["family"]),
        "sources": {key: sources[key] for key in sorted(sources)},
        "records": {key: records[key] for key in sorted(records)},
        "record_count": len(records),
    }


def compare_acceptance_snapshots(previous: dict, current: dict) -> AcceptanceDiff:
    """Compare snapshots and fail if an adapter evolution deletes prior records.

    Additions are expected as new adapters are registered. Changes are surfaced for
    review. Deletions fail closed because they can silently shrink a candidate set.
    """

    if previous.get("aoi_canonical_sha256") != current.get("aoi_canonical_sha256"):
        raise ValueError("acceptance AOI changed; create a new fixture lineage")

    prev = previous.get("records", {})
    cur = current.get("records", {})
    added = tuple(sorted(set(cur) - set(prev)))
    removed = tuple(sorted(set(prev) - set(cur)))
    changed = tuple(
        sorted(
            key
            for key in set(prev) & set(cur)
            if prev[key].get("fingerprint") != cur[key].get("fingerprint")
        )
    )
    if removed:
        raise AssertionError(
            "acceptance candidate-set regression; prior records disappeared: "
            + ", ".join(removed)
        )
    return AcceptanceDiff(added=added, removed=removed, changed=changed)


def write_acceptance_snapshot(path: str | Path, snapshot: dict) -> Path:
    out = Path(path)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return out
