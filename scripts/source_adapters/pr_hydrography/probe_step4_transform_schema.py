from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

TARGETS = [
    "nid36_nhd_candidate_universe_2500m_v2_4.csv",
    "nid36_nhd_ranked_candidates_v2_4.csv",
    "nid36_nhd_top_evidence_ties_v2_4.csv",
    "nid36_nhd_unresolved_v2_4.csv",
    "nid36_nhd_ambiguity_metrics_v2_4.csv",
    "nid36_nhd_relationship_candidate_universe_v3_0.csv",
    "nid36_nhd_relationship_ledger_v3_2.csv",
    "nid36_nhd_relationship_adjudication_queue_v3_0.csv",
    "nid36_to_nhd_candidate_detail.csv",
    "nid36_to_nhd_summary.csv",
]


def locate_unique(root: Path, name: str) -> Path:
    matches = sorted(p for p in root.rglob(name) if p.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one bound replay artifact named {name}; got {len(matches)}")
    return matches[0]


def inspect_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    samples = []
    for row in rows[:2]:
        samples.append({k: row.get(k, "") for k in fields})
    return {
        "path": str(path),
        "row_count": len(rows),
        "column_count": len(fields),
        "columns": fields,
        "sample_rows": samples,
    }


def probe(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f"replay input root missing: {root}")
    artifacts = {}
    for name in TARGETS:
        path = locate_unique(root, name)
        artifacts[name] = inspect_csv(path)
    doc = {
        "schema": "spiderweb.pr_hydrography.step4_transform_schema_probe.v0_1",
        "replay_input_root": str(root),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "downloads_folder_required": False,
        "state": "PASS_STEP4_TRANSFORM_SCHEMA_PROBED",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect frozen resolver/relationship artifact schemas needed for exact Step 4 replay")
    ap.add_argument("--root", default="data/raw/pr_hydrography/historical_2026_08_11/replay_inputs")
    ap.add_argument("--output", default="manifests/pr_hydrography/runtime/step4_transform_schema_probe.json")
    args = ap.parse_args()
    result = probe(Path(args.root), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
