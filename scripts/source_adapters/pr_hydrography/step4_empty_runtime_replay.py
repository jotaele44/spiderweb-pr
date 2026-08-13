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


def _rank_text(row: dict[str, str]) -> str:
    # Historical v2.4 artifacts use different names for the same preserved
    # evidence-rank value depending on artifact role.  `_evidence_rank` is the
    # canonical per-candidate field in the candidate-universe artifacts.
    return _first(
        row,
        "_evidence_rank",
        "evidence_rank",
        "top_evidence_rank",
        "_top_evidence_rank",
    )


def _build_rank_contract(
    preserved_artifacts: list[tuple[str, list[dict[str, str]]]],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    observed: dict[str, set[float]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)
    for artifact_name, rows in preserved_artifacts:
        for row in rows:
            eclass = _eclass(row)
            rank_text = _rank_text(row)
            if not eclass or not rank_text:
                continue
            try:
                rank = float(rank_text)
            except ValueError as exc:
                raise RuntimeError(
                    f"non-numeric preserved evidence rank in {artifact_name}: "
                    f"nid={_first(row, 'nid_id', 'source_a_id')!r} "
                    f"evidence_class={eclass!r} rank={rank_text!r}"
                ) from exc
            observed[eclass].add(rank)
            sources[eclass].add(artifact_name)

    conflicts = {k: sorted(v) for k, v in observed.items() if len(v) != 1}
    if conflicts:
        raise RuntimeError(f"conflicting historical evidence-class rank contract: {conflicts}")

    contract = {k: next(iter(v)) for k, v in observed.items()}
    if not contract:
        raise RuntimeError("preserved replay artifacts yielded no evidence-class rank contract")
    return contract, {k: sorted(v) for k, v in sorted(sources.items())}


def _rank(row: dict[str, str], contract: dict[str, float]) -> float:
    explicit = _rank_text(row)
    if explicit:
        return float(explicit)
    eclass = _eclass(row)
    if not eclass or eclass not in contract:
        raise RuntimeError(f"rank unresolved for nid={_nid(row)} pid={_pid(row)} evidence_class={eclass!r}")
    return contract[eclass]


def _decision(rows: list[dict[str, str]], contract: dict[str, float]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda r: (_rank(r, contract), _pid(r)))
    top_rank = _rank(ordered[0], contract)
    top = [r for r in ordered if _rank(r, contract) == top_rank]
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
    return {
        "candidate_count": len(rows),
        "top_rank": top_rank,
        "top_tie": tie,
        "top_pids": sorted(_pid(r) for r in top),
        "winner_pid": _pid(winner) if winner else None,
        "winner_evidence_class": _eclass(winner) if winner else None,
        "winner_hard_binding": _hard(winner) if winner else False,
        "state": state,
    }


def _signature(d: dict[str, Any]) -> tuple[Any, ...]:
    return (
        d["top_tie"], tuple(d["top_pids"]), d["winner_pid"],
        d["winner_evidence_class"], d["winner_hard_binding"], d["state"],
    )


def _trial_values(known: list[float]) -> list[float]:
    vals = sorted(set(known))
    trials = {vals[0] - 1.0, vals[-1] + 1.0}
    for v in vals:
        trials.add(v)
    for a, b in zip(vals, vals[1:]):
        trials.add((a + b) / 2.0)
    return sorted(trials)


def replay(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    candidate_path = _find(root, "nid36_nhd_candidate_universe_2500m_v2_4.csv")
    ledger_path = _find(root, "nid36_nhd_relationship_ledger_v3_2.csv")
    ranked_path = _find(root, "nid36_nhd_ranked_candidates_v2_4.csv")
    tie_path = _find(root, "nid36_nhd_top_evidence_ties_v2_4.csv")
    unresolved_path = _find(root, "nid36_nhd_unresolved_v2_4.csv")
    relationship_candidate_path = _find(root, "nid36_nhd_relationship_candidate_universe_v3_0.csv")

    candidates = _rows(candidate_path)
    ledger = _rows(ledger_path)
    ranked = _rows(ranked_path)
    ties = _rows(tie_path)
    unresolved = _rows(unresolved_path)
    relationship_candidates = _rows(relationship_candidate_path)

    preserved_artifacts = [
        (candidate_path.name, candidates),
        (ranked_path.name, ranked),
        (tie_path.name, ties),
        (unresolved_path.name, unresolved),
        (ledger_path.name, ledger),
        (relationship_candidate_path.name, relationship_candidates),
    ]
    base_contract, rank_contract_evidence = _build_rank_contract(preserved_artifacts)

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        groups[_nid(row)].append(row)

    candidate_classes = sorted({_eclass(r) for r in candidates if _eclass(r)})
    unknown_classes = sorted(set(candidate_classes) - set(base_contract))
    if len(unknown_classes) > 1:
        raise RuntimeError(f"multiple unpreserved evidence classes require multidimensional sensitivity replay: {unknown_classes}")

    sensitivity: dict[str, Any] = {}
    chosen_contract = dict(base_contract)
    if unknown_classes:
        unknown = unknown_classes[0]
        affected = sorted(nid for nid, rows in groups.items() if any(_eclass(r) == unknown for r in rows))
        trials = _trial_values(list(base_contract.values()))
        per_trial = []
        signatures_by_nid: dict[str, set[tuple[Any, ...]]] = {nid: set() for nid in affected}
        for trial in trials:
            contract = {**base_contract, unknown: trial}
            trial_decisions = {nid: _decision(groups[nid], contract) for nid in affected}
            for nid, d in trial_decisions.items():
                signatures_by_nid[nid].add(_signature(d))
            per_trial.append({"assigned_rank": trial, "decisions": [{"nid_id": n, **trial_decisions[n]} for n in affected]})
        invariant = all(len(sigs) == 1 for sigs in signatures_by_nid.values())
        sensitivity = {
            "unknown_class": unknown,
            "affected_nids": affected,
            "trial_ranks_cover_all_order_and_tie_regimes": trials,
            "decision_invariant_across_all_rank_regimes": invariant,
            "distinct_decision_signature_count_by_nid": {n: len(s) for n, s in signatures_by_nid.items()},
            "trials": per_trial,
        }
        if not invariant:
            report = {
                "schema": "spiderweb.pr_hydrography.step4_empty_runtime_replay.v0_4",
                "snapshot_root": str(root),
                "downloads_folder_required": False,
                "network_required": False,
                "replay_scope": "LOGICAL_DECISION_PROJECTION_FROM_PRESERVED_RANK_FIELDS",
                "historical_transform_source_code_preserved": False,
                "byte_identical_regeneration_claimed": False,
                "rank_contract_source": "ALL_BOUND_HISTORICAL_ARTIFACTS_WITH_EXPLICIT_RANK_FIELDS",
                "rank_contract": dict(sorted(base_contract.items())),
                "rank_contract_evidence": rank_contract_evidence,
                "unpreserved_rank_classes": unknown_classes,
                "rank_uncertainty_sensitivity": sensitivity,
                "state": "BLOCKED_STEP4_RANK_UNCERTAINTY_CHANGES_DECISION",
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            return report
        chosen_contract[unknown] = trials[0]

    replayed = {nid: {"nid_id": nid, **_decision(rows, chosen_contract)} for nid, rows in sorted(groups.items())}
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
        if decision["winner_pid"] is not None and frozen_pid != decision["winner_pid"]:
            mismatches.append({"nid_id": nid, "field": "winner_pid", "replayed": decision["winner_pid"], "frozen": frozen_pid})
        top_classes = {_eclass(r) for r in groups[nid] if _pid(r) in decision["top_pids"]}
        if not (top_classes & set(unknown_classes)):
            frozen_rank = _first(frozen, "top_evidence_rank", "evidence_rank", "_top_evidence_rank", "_evidence_rank")
            if frozen_rank and float(frozen_rank) != decision["top_rank"]:
                mismatches.append({"nid_id": nid, "field": "top_evidence_rank", "replayed": decision["top_rank"], "frozen": float(frozen_rank)})
        frozen_hard = _truth(_first(frozen, "v4_hard_binding", "explicit_hard_binding", "hard_binding"))
        if decision["winner_pid"] is not None and frozen_hard != decision["winner_hard_binding"]:
            mismatches.append({"nid_id": nid, "field": "hard_binding", "replayed": decision["winner_hard_binding"], "frozen": frozen_hard})

    for nid in sorted(set(frozen_by_nid) - set(replayed)):
        mismatches.append({"nid_id": nid, "field": "candidate_group", "replayed": "missing", "frozen": "present"})

    denominator = {
        "candidate_groups": len(groups),
        "candidate_rows": len(candidates),
        "relationship_candidate_rows": len(relationship_candidates),
        "ledger_rows": len(ledger),
        "ranked_rows": len(ranked),
        "tie_rows": len(ties),
        "unresolved_rows": len(unresolved),
    }
    denominator_pass = len(groups) == 36 and len(ledger) == 36
    sensitivity_pass = not unknown_classes or sensitivity.get("decision_invariant_across_all_rank_regimes") is True

    report = {
        "schema": "spiderweb.pr_hydrography.step4_empty_runtime_replay.v0_4",
        "snapshot_root": str(root),
        "downloads_folder_required": False,
        "network_required": False,
        "replay_scope": "LOGICAL_DECISION_PROJECTION_FROM_PRESERVED_RANK_FIELDS",
        "historical_transform_source_code_preserved": False,
        "byte_identical_regeneration_claimed": False,
        "rank_contract_source": "ALL_BOUND_HISTORICAL_ARTIFACTS_WITH_EXPLICIT_RANK_FIELDS",
        "rank_contract": dict(sorted(base_contract.items())),
        "rank_contract_evidence": rank_contract_evidence,
        "unpreserved_rank_classes": unknown_classes,
        "rank_uncertainty_sensitivity": sensitivity,
        "rank_uncertainty_invariant": sensitivity_pass,
        "denominator": denominator,
        "denominator_pass": denominator_pass,
        "decision_mismatch_count": len(mismatches),
        "decision_mismatches": mismatches,
        "replayed_decisions": [replayed[k] for k in sorted(replayed)],
        "state": "PASS_STEP4_EMPTY_RUNTIME_LOGICAL_REPLAY" if denominator_pass and sensitivity_pass and not mismatches else "BLOCKED_STEP4_EMPTY_RUNTIME_LOGICAL_REPLAY",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False, prefix=f".{output.name}.") as tmp:
        json.dump(report, tmp, indent=2, ensure_ascii=False, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(output)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay historical NID→NHD decisions from bound snapshot inputs only")
    ap.add_argument("--root", default="data/raw/pr_hydrography/historical_2026_08_11/replay_inputs")
    ap.add_argument("--output", default="manifests/pr_hydrography/runtime/step4_empty_runtime_replay.json")
    args = ap.parse_args()
    report = replay(Path(args.root), Path(args.output))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["state"].startswith("PASS_") else 9


if __name__ == "__main__":
    raise SystemExit(main())
