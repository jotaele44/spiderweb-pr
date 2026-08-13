from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^([0-9a-fA-F]{64})\s+[* ]?(.*)$")
NON_SEMANTIC_NAMES = {".DS_Store"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_sha_manifest(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = SHA_RE.match(line.strip())
        if not m:
            continue
        digest, raw_name = m.groups()
        name = raw_name.strip().lstrip("*")
        rows.append({"sha256": digest.lower(), "name": name})
    return rows


def locate_candidates(name: str, historical_root: Path, source_root: Path) -> list[Path]:
    base = Path(name).name
    found: set[Path] = set()
    for root in (historical_root, source_root):
        if not root.exists():
            continue
        exact = root / name
        if exact.is_file():
            found.add(exact.resolve())
        for p in root.rglob(base):
            if p.is_file():
                found.add(p.resolve())
    return sorted(found)


def audit(historical_root: Path, source_root: Path, output: Path) -> dict[str, Any]:
    historical_root = historical_root.resolve()
    source_root = source_root.resolve()
    prov = historical_root / "provenance_manifests"
    manifests = sorted(prov.rglob("*SHA256SUMS*.txt"))
    if not manifests:
        raise RuntimeError(f"no preserved SHA256SUMS manifests found under {prov}")

    references: list[dict[str, Any]] = []
    for manifest in manifests:
        for row in parse_sha_manifest(manifest):
            candidates = locate_candidates(row["name"], historical_root, source_root)
            candidate_rows = []
            exact_matches = []
            for p in candidates:
                actual = sha256_file(p)
                state = "EXACT_HASH_MATCH" if actual == row["sha256"] else "HASH_MISMATCH"
                candidate_rows.append({
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "actual_sha256": actual,
                    "state": state,
                    "location": "SNAPSHOT_STORE" if historical_root in p.parents else "SOURCE_ROOT",
                })
                if state == "EXACT_HASH_MATCH":
                    exact_matches.append(p)

            non_semantic = Path(row["name"]).name in NON_SEMANTIC_NAMES
            if non_semantic:
                reference_state = "IGNORED_NON_SEMANTIC_METADATA"
            elif any(historical_root in p.parents for p in exact_matches):
                reference_state = "BOUND_IN_SNAPSHOT_STORE"
            elif exact_matches:
                reference_state = "AVAILABLE_FOR_BINDING"
            else:
                reference_state = "MISSING_OR_HASH_MISMATCH"

            references.append({
                "manifest": str(manifest.relative_to(historical_root)),
                "referenced_name": row["name"],
                "expected_sha256": row["sha256"],
                "candidates": candidate_rows,
                "exact_match_count": len(exact_matches),
                "snapshot_exact_match": any(historical_root in p.parents for p in exact_matches),
                "source_root_exact_match": any(source_root in p.parents for p in exact_matches),
                "non_semantic_metadata": non_semantic,
                "state": reference_state,
            })

    unique_keys = {(r["expected_sha256"], r["referenced_name"]) for r in references}
    ignored = [r for r in references if r["state"] == "IGNORED_NON_SEMANTIC_METADATA"]
    missing = [r for r in references if r["state"] == "MISSING_OR_HASH_MISMATCH"]
    available = [r for r in references if r["state"] == "AVAILABLE_FOR_BINDING"]
    bound = [r for r in references if r["state"] == "BOUND_IN_SNAPSHOT_STORE"]

    doc = {
        "schema": "spiderweb.pr_hydrography.replay_input_audit.v0_2",
        "historical_root": str(historical_root),
        "source_root": str(source_root),
        "sha_manifest_count": len(manifests),
        "reference_row_count": len(references),
        "unique_reference_count": len(unique_keys),
        "bound_in_snapshot_store": len(bound),
        "available_for_binding": len(available),
        "missing_or_hash_mismatch": len(missing),
        "ignored_non_semantic_metadata": len(ignored),
        "ignored_names": sorted({r["referenced_name"] for r in ignored}),
        "references": references,
        "step4_replay_input_state": (
            "PASS_REPLAY_INPUTS_COMPLETE" if not missing and not available
            else "OPEN_REPLAY_INPUTS_REQUIRE_BINDING" if not missing
            else "BLOCKED_REPLAY_INPUTS_INCOMPLETE"
        ),
        "zero_silent_substitution": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit preserved SHA manifests for deterministic Step 4 replay inputs")
    ap.add_argument("--historical-root", default="data/raw/pr_hydrography/historical_2026_08_11")
    ap.add_argument("--source-root", default="/Users/jotaele/Downloads/PR_RESERVOIR_DATA")
    ap.add_argument("--output", default="manifests/pr_hydrography/runtime/step4_replay_input_audit.json")
    args = ap.parse_args()
    result = audit(Path(args.historical_root), Path(args.source_root), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["step4_replay_input_state"] == "PASS_REPLAY_INPUTS_COMPLETE" else 8


if __name__ == "__main__":
    raise SystemExit(main())
