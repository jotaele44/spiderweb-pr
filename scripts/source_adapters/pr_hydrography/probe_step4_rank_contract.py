from __future__ import annotations

import argparse
import csv
import json
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


def _first(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row and str(row[name]).strip() != "":
            return str(row[name]).strip()
    return ""


def _walk(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.append((p, v))
            out.extend(_walk(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}[{i}]"
            out.append((p, v))
            out.extend(_walk(v, p))
    return out


def probe(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    candidate_path = _find(root, "nid36_nhd_candidate_universe_2500m_v2_4.csv")
    ranked_path = _find(root, "nid36_nhd_ranked_candidates_v2_4.csv")
    baseline_path = _find(root, "resolver_v2_1_input_baseline.json")

    candidates = _rows(candidate_path)
    ranked = _rows(ranked_path)

    candidate_classes: dict[str, dict[str, Any]] = {}
    for row in candidates:
        eclass = _first(row, "evidence_class")
        if not eclass:
            continue
        rec = candidate_classes.setdefault(eclass, {"candidate_rows": 0, "explicit_ranks": set(), "sample_nids": []})
        rec["candidate_rows"] += 1
        rank_text = _first(row, "evidence_rank", "top_evidence_rank")
        if rank_text:
            rec["explicit_ranks"].add(float(rank_text))
        nid = _first(row, "nid_id", "source_a_id")
        if nid and nid not in rec["sample_nids"] and len(rec["sample_nids"]) < 5:
            rec["sample_nids"].append(nid)

    ranked_contract: dict[str, set[float]] = defaultdict(set)
    for row in ranked:
        eclass = _first(row, "evidence_class")
        rank_text = _first(row, "evidence_rank", "top_evidence_rank")
        if eclass and rank_text:
            ranked_contract[eclass].add(float(rank_text))

    candidate_class_rows = []
    missing_from_ranked = []
    for eclass in sorted(candidate_classes):
        explicit = sorted(candidate_classes[eclass]["explicit_ranks"])
        ranked_ranks = sorted(ranked_contract.get(eclass, set()))
        row = {
            "evidence_class": eclass,
            "candidate_rows": candidate_classes[eclass]["candidate_rows"],
            "candidate_explicit_ranks": explicit,
            "ranked_artifact_ranks": ranked_ranks,
            "sample_nids": candidate_classes[eclass]["sample_nids"],
        }
        candidate_class_rows.append(row)
        if not explicit and not ranked_ranks:
            missing_from_ranked.append(eclass)

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    policy_hits = []
    keywords = ("rank", "evidence", "distance", "hard", "name", "point", "radius", "class")
    for path, value in _walk(baseline):
        low = path.lower()
        if any(k in low for k in keywords):
            if isinstance(value, (str, int, float, bool)) or value is None:
                policy_hits.append({"path": path, "value": value})

    cert_hits = []
    cert_matches = sorted(root.parent.rglob("nid36_nhd_candidate_resolver_v2_4_certification.json"))
    if cert_matches:
        cert = json.loads(cert_matches[0].read_text(encoding="utf-8"))
        for path, value in _walk(cert):
            low = path.lower()
            if any(k in low for k in keywords):
                if isinstance(value, (str, int, float, bool)) or value is None:
                    cert_hits.append({"path": path, "value": value})

    conflicts = {
        eclass: sorted(ranks)
        for eclass, ranks in ranked_contract.items()
        if len(ranks) > 1
    }

    doc = {
        "schema": "spiderweb.pr_hydrography.step4_rank_contract_probe.v0_1",
        "candidate_class_count": len(candidate_class_rows),
        "candidate_classes": candidate_class_rows,
        "ranked_contract_conflicts": conflicts,
        "classes_missing_numeric_rank_contract": missing_from_ranked,
        "baseline_policy_hits": policy_hits,
        "certification_policy_hits": cert_hits,
        "downloads_folder_required": False,
        "state": "PASS_STEP4_RANK_CONTRACT_PROBED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover historical evidence-class rank contract for Step 4 replay")
    ap.add_argument("--root", default="data/raw/pr_hydrography/historical_2026_08_11/replay_inputs")
    ap.add_argument("--output", default="manifests/pr_hydrography/runtime/step4_rank_contract_probe.json")
    args = ap.parse_args()
    doc = probe(Path(args.root), Path(args.output))
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
