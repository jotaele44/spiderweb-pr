from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bind(audit_path: Path, historical_root: Path, output: Path) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("missing_or_hash_mismatch", 0) != 0:
        raise RuntimeError("replay binding blocked: audit contains missing/hash-mismatch semantic references")

    available = [r for r in audit.get("references", []) if r.get("state") == "AVAILABLE_FOR_BINDING"]
    historical_root = historical_root.resolve()
    target_root = historical_root / "replay_inputs"
    if target_root.exists():
        raise FileExistsError(f"replay input destination already exists: {target_root}")

    stage = Path(tempfile.mkdtemp(prefix=".replay_inputs-", dir=str(historical_root)))
    copied: list[dict[str, Any]] = []
    try:
        for ref in available:
            expected = ref["expected_sha256"]
            exact_source = None
            for candidate in ref.get("candidates", []):
                if candidate.get("location") == "SOURCE_ROOT" and candidate.get("state") == "EXACT_HASH_MATCH":
                    exact_source = Path(candidate["path"])
                    break
            if exact_source is None:
                raise RuntimeError(f"no exact source-root candidate for {ref['referenced_name']}")

            # Preserve manifest-relative naming under a collision-safe digest namespace.
            rel_name = Path(ref["referenced_name"])
            digest_dir = stage / expected[:16]
            target = digest_dir / rel_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(exact_source, target)
            actual = sha256_file(target)
            if actual != expected:
                raise RuntimeError(f"post-copy hash mismatch for {target}")
            copied.append({
                "referenced_name": ref["referenced_name"],
                "manifest": ref["manifest"],
                "source_path": str(exact_source),
                "bound_relative_path": str(Path("replay_inputs") / expected[:16] / rel_name),
                "bytes": target.stat().st_size,
                "sha256": actual,
                "binding_state": "EXACT_HASH_MATCH",
            })

        os.replace(stage, target_root)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    document = {
        "schema": "spiderweb.pr_hydrography.replay_input_binding.v0_1",
        "audit": str(audit_path),
        "historical_root": str(historical_root),
        "destination": str(target_root),
        "semantic_reference_count": len(available) + int(audit.get("bound_in_snapshot_store", 0)),
        "newly_bound_count": len(copied),
        "ignored_non_semantic_metadata": int(audit.get("ignored_non_semantic_metadata", 0)),
        "copied": copied,
        "historical_bytes_reencoded": False,
        "zero_silent_substitution": True,
        "state": "PASS_REPLAY_INPUTS_BOUND",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document


def main() -> int:
    ap = argparse.ArgumentParser(description="Atomically bind exact historical Step 4 replay inputs")
    ap.add_argument("--audit", default="manifests/pr_hydrography/runtime/step4_replay_input_audit.json")
    ap.add_argument("--historical-root", default="data/raw/pr_hydrography/historical_2026_08_11")
    ap.add_argument("--output", default="manifests/pr_hydrography/runtime/step4_replay_input_binding.json")
    args = ap.parse_args()
    result = bind(Path(args.audit), Path(args.historical_root), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
