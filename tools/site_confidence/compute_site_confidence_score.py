#!/usr/bin/env python3
"""Evidence-linked site confidence scoring.

Reads a CSV evidence ledger and computes transparent additive scores.
No heuristic score is allowed without an evidence row.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SCORE_RULES = {
    "visible_structure": 2,
    "canopy_concealment": 1,
    "service_access_within_50m": 2,
    "larger_lidar_pad": 3,
    "trench_or_linear_buried_signature": 3,
    "utility_convergence": 3,
    "hydro_karst_transition": 1,
    "parcel_permit_mismatch": 3,
    "normal_golf_utility_match": -3,
    "no_terrain_modification": -3,
    "abandoned_or_stable_no_activity": -2,
}


def classify(score: int) -> str:
    if score <= 3:
        return "low-interest / likely ordinary"
    if score <= 7:
        return "monitor / contextual infrastructure"
    if score <= 11:
        return "high-interest utility node"
    return "anomalous infrastructure candidate requiring deeper validation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-id", required=True)
    args = parser.parse_args()

    site_dir = Path("data") / "sites" / args.site_id
    evidence_path = site_dir / "site_observations.csv"

    score = 0
    applied = []

    if evidence_path.exists():
        with evidence_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                factor = row.get("factor", "").strip()
                evidence_status = row.get("evidence_status", "pending").strip()
                if factor in SCORE_RULES and evidence_status == "confirmed":
                    delta = SCORE_RULES[factor]
                    score += delta
                    applied.append({
                        "factor": factor,
                        "delta": delta,
                        "evidence": row.get("notes", "")
                    })

    result = {
        "site_id": args.site_id,
        "score": score,
        "classification": classify(score),
        "applied_factors": applied,
        "ruleset_version": "site_confidence_v1"
    }

    out_dir = Path("outputs") / "site_scores"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.site_id}_score.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
