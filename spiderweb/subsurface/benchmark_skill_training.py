"""Fail-closed training/registration gate for certified subsurface benchmarks.

A benchmark implementation, source-discovery result, or provisional run is not training
evidence. The reusable skill descriptor can only be emitted from a PASS benchmark with
zero unresolved candidate residue and a frozen evidence manifest hash.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .benchmark import CandidateObject, ObjectState, certification_state, validate_benchmark


@dataclass(frozen=True)
class SkillReceipt:
    schema: str
    skill_id: str
    benchmark_id: str
    benchmark_config_sha256: str
    evidence_manifest_sha256: str
    training_rows: int
    candidate_ids: tuple[str, ...]
    capability_boundary: tuple[str, ...]
    descriptor_sha256: str


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_skill_receipt(
    *,
    benchmark_payload: dict,
    benchmark_config_bytes: bytes,
    evidence_manifest_sha256: str,
    candidates: Iterable[CandidateObject],
    skill_id: str = "spiderweb-subsurface-karst-cave-void-ocean-outlet",
) -> SkillReceipt:
    """Create a hash-bound skill receipt only from a certified benchmark."""
    validate_benchmark(benchmark_payload)
    rows = tuple(candidates)
    if certification_state(benchmark_payload, rows) != "PASS":
        raise ValueError("skill training requires benchmark certification PASS")
    unresolved = [row.candidate_id for row in rows if row.state == ObjectState.UNRESOLVED]
    if unresolved:
        raise ValueError(f"unresolved candidate residue: {unresolved}")
    if len(evidence_manifest_sha256) != 64:
        raise ValueError("evidence manifest SHA-256 is required")
    for row in rows:
        row.validate()

    descriptor = {
        "schema": "spiderweb.subsurface.reusable_skill.v1",
        "skill_id": skill_id,
        "benchmark_id": benchmark_payload["benchmark_id"],
        "benchmark_config_sha256": _sha256(benchmark_config_bytes),
        "evidence_manifest_sha256": evidence_manifest_sha256,
        "training_rows": len(rows),
        "candidate_ids": sorted(row.candidate_id for row in rows),
        "capability_boundary": [
            "surface_morphology_screening",
            "karst_candidate_generation",
            "depression_flow_lineament_analysis",
            "land_to_ocean_corridor_screening",
            "temporal_persistence",
            "false_positive_adjudication",
        ],
    }
    descriptor_sha = _sha256(_canonical_bytes(descriptor))
    return SkillReceipt(
        schema=descriptor["schema"],
        skill_id=skill_id,
        benchmark_id=descriptor["benchmark_id"],
        benchmark_config_sha256=descriptor["benchmark_config_sha256"],
        evidence_manifest_sha256=evidence_manifest_sha256,
        training_rows=len(rows),
        candidate_ids=tuple(descriptor["candidate_ids"]),
        capability_boundary=tuple(descriptor["capability_boundary"]),
        descriptor_sha256=descriptor_sha,
    )


def write_skill_receipt(path: str | Path, receipt: SkillReceipt) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(receipt)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
