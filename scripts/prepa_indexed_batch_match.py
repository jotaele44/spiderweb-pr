#!/usr/bin/env python3
"""Indexed full-universe PREPA stakeholder matcher.

Purpose:
- scale PREPA Title III stakeholder matching beyond targeted subsets
- avoid O(N*M) all-pairs matching
- use token blocking to preselect candidates
- checkpoint completed stakeholder batches
- emit append-safe correlation flags

Inputs:
- canonical PREPA stakeholder CSV
- one or more normalized procurement CSVs

Outputs:
- correlation_flags.csv
- checkpoint.json
- run_summary.json

This produces correlation leads only. It does not infer misconduct.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

STOPWORDS = {
    "THE", "AND", "OF", "DE", "DEL", "LA", "LAS", "LOS", "INC", "LLC", "LLP", "PSC", "CORP", "CORPORATION",
    "COMPANY", "CO", "SA", "SE", "LP", "LTD", "PUERTO", "RICO", "PR", "SERVICES", "SERVICE"
}

NAME_FIELDS = (
    "recipient_name", "vendor_name", "contractor", "awardee", "entity_name", "name", "legal_business_name",
    "recipient_parent_name", "prime_awardee_name", "subawardee_name", "Contratista", "CONTRACTOR NAME"
)

ID_FIELDS = ("record_id", "award_id", "piid", "contract_number", "Número de Contrato", "Project_ID", "id")
DATE_FIELDS = ("action_date", "award_date", "date_signed", "Fecha de Inicio", "Fecha de Otorgación", "transaction_obligated_date")


def normalize(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 ]+", " ", str(value).upper())
    value = re.sub(r"\s+", " ", value).strip()
    return value


def tokens(value: str) -> set[str]:
    return {t for t in normalize(value).split() if len(t) >= 3 and t not in STOPWORDS}


def blocking_keys(value: str, max_keys: int = 8) -> list[str]:
    toks = sorted(tokens(value), key=lambda t: (-len(t), t))
    return toks[:max_keys]


def overlap_score(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def choose_name(record: dict[str, Any]) -> str:
    for field in NAME_FIELDS:
        if record.get(field):
            return str(record[field])
    return ""


def choose_id(record: dict[str, Any], fallback: int) -> str:
    for field in ID_FIELDS:
        if record.get(field):
            return str(record[field])
    return f"row:{fallback}"


def choose_date(record: dict[str, Any]) -> str:
    for field in DATE_FIELDS:
        if record.get(field):
            return str(record[field])[:10]
    return ""


def build_dataset_index(dataset_path: Path) -> tuple[dict[str, list[int]], list[dict[str, str]]]:
    rows = load_csv(dataset_path)
    index: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        name = choose_name(row)
        if not name:
            continue
        for key in blocking_keys(name):
            index[key].append(idx)
    return index, rows


def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(payload.get("completed_entity_ids", []))


def save_checkpoint(path: Path, completed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"completed_entity_ids": sorted(completed)}, indent=2), encoding="utf-8")


def entity_id(name: str) -> str:
    return "prepa:" + re.sub(r"[^a-z0-9]+", "_", normalize(name).lower()).strip("_")[:180]


def candidate_indices(name: str, index: dict[str, list[int]], max_candidates: int) -> list[int]:
    counts: dict[int, int] = defaultdict(int)
    for key in blocking_keys(name):
        for idx in index.get(key, []):
            counts[idx] += 1
    ranked = sorted(counts, key=lambda i: counts[i], reverse=True)
    return ranked[:max_candidates]


def append_flags(path: Path, flags: list[dict[str, Any]]) -> None:
    fields = [
        "entity_id", "entity_name", "matched_dataset", "matched_record_id", "matched_name", "match_score",
        "record_date", "evidence_tier", "analytic_label"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows(flags)


def run(stakeholders: list[dict[str, str]], dataset_paths: list[Path], outdir: Path, threshold: float, batch_size: int, max_candidates: int) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = outdir / "checkpoint.json"
    flags_path = outdir / "correlation_flags.csv"
    completed = load_checkpoint(checkpoint_path)

    indexes = []
    for dataset_path in dataset_paths:
        index, rows = build_dataset_index(dataset_path)
        indexes.append((dataset_path.name, index, rows))

    emitted = 0
    processed = 0
    for row in stakeholders:
        name = row.get("entity_name") or row.get("normalized_name") or row.get("name") or ""
        if not name:
            continue
        eid = entity_id(name)
        if eid in completed:
            continue
        batch_flags: list[dict[str, Any]] = []
        for dataset_name, index, records in indexes:
            for idx in candidate_indices(name, index, max_candidates=max_candidates):
                record = records[idx]
                candidate_name = choose_name(record)
                score = overlap_score(name, candidate_name)
                if score >= threshold:
                    batch_flags.append({
                        "entity_id": eid,
                        "entity_name": normalize(name),
                        "matched_dataset": dataset_name,
                        "matched_record_id": choose_id(record, idx),
                        "matched_name": normalize(candidate_name),
                        "match_score": round(score, 4),
                        "record_date": choose_date(record),
                        "evidence_tier": "T1_technical_primary",
                        "analytic_label": "correlation_not_allegation",
                    })
        if batch_flags:
            append_flags(flags_path, batch_flags)
            emitted += len(batch_flags)
        completed.add(eid)
        processed += 1
        if processed % batch_size == 0:
            save_checkpoint(checkpoint_path, completed)
    save_checkpoint(checkpoint_path, completed)

    summary = {
        "stakeholders_total": len(stakeholders),
        "stakeholders_processed_this_run": processed,
        "completed_total": len(completed),
        "flags_emitted_this_run": emitted,
        "flags_csv": str(flags_path),
        "checkpoint": str(checkpoint_path),
        "threshold": threshold,
        "max_candidates_per_dataset": max_candidates,
    }
    (outdir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run indexed PREPA stakeholder matching with checkpoints")
    parser.add_argument("--stakeholders", required=True, type=Path)
    parser.add_argument("--datasets", nargs="+", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.72)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--max-candidates", type=int, default=500)
    args = parser.parse_args()

    stakeholders = load_csv(args.stakeholders)
    summary = run(stakeholders, args.datasets, args.outdir, args.threshold, args.batch_size, args.max_candidates)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
