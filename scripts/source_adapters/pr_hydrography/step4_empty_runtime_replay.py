from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


def _find(root: Path, name: str) -> Path:
    matches = sorted(p for p in root.rglob(name) if p.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one bound {name}; got {len(matches)}")
    return matches[0]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _truth(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def _first(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row and str(row[name]).strip() != "":
            return str(row[name]).strip()
    return ""


def _rank(row: dict[str, str]) -> float:
    value = _first(row, "evidence_rank", "top_evidence_rank")
    if value == "":
        raise RuntimeError("candidate row has no evidence rank")
    return float(value)


def _nid(row: dict[str, str]) -> str:
    value = _first(row, "nid_id", "source_a_id")
    if not value:
        raise RuntimeError("candidate row has no NID/source_a identifier")
    return value


def _pid(row: dict[str, str]) -> str:
    value = _first(row, "nhd_permanent_identifier", "source_b_id")
    if not value:
        raise RuntimeError("candidate row has no NHD/source_b identifier")
    return value


def _hard(row: dict[str, str]) -> bool:
    return _truth(_first(row, "v4_hard_binding", "explicit_hard_binding", "hard_binding"))


def _eclass(row: dict[str, str]) -> str:
    return _first(row, "evidence_class")


def replay(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    # All reads are intentionally constrained to the snapshot store.
    candidate_path = _find(root, "nid36_nhd_candidate_universe_2500m_v2_4.csv")
    ledger_path = _find(root, "nid36_nhd_relationship_ledger_v3_2.csv")
    ranked_path = _find(root, "nid36_nhd_ranked_candidates_v2_4.csv")
    tie_path = _find(root, "nid36_nhd_top_evidence_ties_v2_4.csv")
    unresolved_path = _find(root, "nid36_nhd_unresolved_v2_4.csv")

    candidates = _rows(candidate_path)
    ledger = _rows(ledger_path)
    ranked = _rows(ranked_path)
    ties = _rows(tie_path)
    unresolved = _rows(unresolved_path)

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        groups[_nid(row)].append(row)

    replayed: dict[str, dict[str, Any]] = {}
    for nid, rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda r: (_rank(r), _pid(r)))
        top_rank = _rank(ordered[0])
        top = [r for r in ordered if _rank(r) == top_rank]
        tie = len(top) > 1
        winner = None
        state = "TOP_EVIDENCE_TIE" if tie else ""
        if not tie:
            candidate = top[0]
            if _hard(candidate):
                winner = candidate
                state = "PREFERRED_HARD_BINDING"
            elif _eclass(candidate).upper().startswith("DISTANCE_ONLY"):
                state = "UNRESOLVED_PROXIMITY_ONLY"
            else:
                winner = candidate
                state = "PREFERRED_EVIDENCE_WINNER"
        replayed[nid] = {
            "nid_id": nid,
            "candidate_count": len(rows),
            "top_rank": top_rank,
            "top_tie": tie,
            "top_pids": sorted(_pid(r) for r in top),
            "winner_pid": _pid(winner) if winner else None,
            "winner_evidence_class": _eclass(winner) if winner else None,
            "winner_hard_binding": _hard(winner) if winner else False,
            "state": state,
        }

    frozen_by_nid = {_nid(row): row for row in ledger}
    mismatches: list[dict[str, Any]] = []
    for nid, decision in replayed.items():
        frozen = frozen_by_nid.get(nid)
        if frozen is None:
            mismatches.append({"nid_id": nid, "field": "ledger_row", "replayed": "present", "frozen": "missing"})
            continue
        frozen_tie = _truth(_first(frozen, "top_evidence_tie"))
        if frozen_tie != decision["top_tie"]:
            mismatches.append({"nid_id": nid, "field": "top_evidence_tie", "replayed": decision["top_tie"], "frozen": frozen_tie})
        frozen_pid = _first(frozen, "nhd_permanent_identifier", "source_b_id") or None
        # A frozen row may retain its top candidate even when unresolved/tied; only
        # require winner equality when replay logic produces an actual winner.
        if decision["winner_pid"] is not None and frozen_pid != decision["winner_pid"]:
            mismatches.append({"nid_id": nid, "field": "winner_pid", "replayed": decision["winner_pid"], "frozen": frozen_pid})
        frozen_rank = _first(frozen, "top_evidence_rank", "evidence_rank")
        if frozen_rank and float(frozen_rank) != decision["top_rank"]:
            mismatches.append({"nid_id": nid, "field": "top_evidence_rank", "replayed": decision["top_rank"], "frozen": float(frozen_rank)})
        frozen_hard = _truth(_first(frozen, "v4_hard_binding", "explicit_hard_binding", "hard_binding"))
        if decision["winner_pid"] is not None and frozen_hard != decision["winner_hard_binding"]:
            mismatches.append({"nid_id": nid, "field": "hard_binding", "replayed": decision["winner_hard_binding"], "frozen": frozen_hard})

    extra_frozen = sorted(set(frozen_by_nid) - set(replayed))
    for nid in extra_frozen:
        mismatches.append({"nid_id": nid, "field": "candidate_group", "replayed": "missing", "frozen": "present"})

    # Secondary denominator checks make accidental partial replay impossible.
    denominator = {
        "candidate_groups": len(groups),
        "ledger_rows": len(ledger),
        "ranked_rows": len(ranked),
        "tie_rows": len(ties),
        "unresolved_rows": len(unresolved),
    }
    denominator_pass = len(groups) == 36 and len(ledger) == 36

    report = {
        "schema": "spiderweb.pr_hydrography.step4_empty_runtime_replay.v0_1",
        "snapshot_root": str(root),
        "downloads_folder_required": False,
        "network_required": False,
        "replay_scope": "LOGICAL_DECISION_PROJECTION",
        "historical_transform_source_code_preserved": False,
        "byte_identical_regeneration_claimed": False,
        "denominator": denominator,
        "denominator_pass": denominator_pass,
        "decision_mismatch_count": len(mismatches),
        "decision_mismatches": mismatches,
        "replayed_decisions": [replayed[k] for k in sorted(replayed)],
        "state": "PASS_STEP4_EMPTY_RUNTIME_LOGICAL_REPLAY" if denominator_pass and not mismatches else "BLOCKED_STEP4_EMPTY_RUNTIME_LOGICAL_REPLAY",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False, prefix=f".{output.name}.") as tmp:
        json.dump(report, tmp, indent=2, ensure_ascii=False, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(output)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay historical NID→NHD decision logic from bound snapshot inputs only")
    ap.add_argument("--root", default="data/raw/pr_hydrography/historical_2026_08_11/replay_inputs")
    ap.add_argument("--output", default="manifests/pr_hydrography/runtime/step4_empty_runtime_replay.json")
    args = ap.parse_args()
    report = replay(Path(args.root), Path(args.output))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["state"].startswith("PASS_") else 9


if __name__ == "__main__":
    raise SystemExit(main())
