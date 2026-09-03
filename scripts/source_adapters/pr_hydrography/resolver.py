from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core import CandidateRelationship, rank_candidates, select_candidates, strict_bool


def _candidate(row: dict[str, Any]) -> CandidateRelationship:
    required = {"source_a_id", "source_b_id", "evidence_class", "evidence_rank"}
    missing = required - set(row)
    if missing:
        raise RuntimeError(f"candidate row missing fields: {sorted(missing)}")
    return CandidateRelationship(
        source_a_id=str(row["source_a_id"]),
        source_b_id=str(row["source_b_id"]),
        evidence_class=str(row["evidence_class"]),
        evidence_rank=int(row["evidence_rank"]),
        distance_m=None if row.get("distance_m") in {None, ""} else float(row["distance_m"]),
        explicit_hard_binding=strict_bool(row.get("explicit_hard_binding", False)),
        source_taxonomy=str(row.get("source_taxonomy", "")),
    )


def resolve_document(document: dict[str, Any]) -> dict[str, Any]:
    discovery = [_candidate(row) for row in document.get("discovery_candidates", [])]
    explicit = [_candidate(row) for row in document.get("explicit_evidence_candidates", [])]
    candidates = select_candidates(discovery, explicit)
    grouped: dict[str, list[CandidateRelationship]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.source_a_id, []).append(candidate)
    results = []
    for source_a_id in sorted(grouped):
        ranked = rank_candidates(grouped[source_a_id])
        results.append({
            "source_a_id": source_a_id,
            "state": ranked["state"],
            "winner": asdict(ranked["winner"]) if ranked["winner"] else None,
            "top": [asdict(row) for row in ranked["top"]],
            "candidate_count": len(grouped[source_a_id]),
        })
    return {
        "schema": "spiderweb.pr_hydrography.relationship_resolution.v0_1",
        "universe_contract": {
            "source_taxonomy_is_identity": False,
            "nearest_is_identity": False,
            "deterministic_order_is_evidence": False,
            "candidate_set_rule": "DISCOVERY_UNION_EXPLICIT_HIGHER_GRADE_EVIDENCE",
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve cross-source relationship candidates without conflating source universes")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    document = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = resolve_document(document)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
