from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import sha256_file

EXPECTED = {
    "USGS_NHD_WATERBODY/nhd_pr_lakepond_reservoir.gpkg": "08a216d247a1ed7a59046d94a4a8f858ffbd9e9164175ce8927ccd8e791cc45a",
    "USACE_NID_DAMS/nid_nation.csv": "67890b6bc0eca8976fa646080bc527a619b8729166dcf7bf7ec694db1bb3f82e",
    "USGS_INLAND_BATHY_V4/USGS_InlandBathyResearch_Invent_v4.gdb.zip": "40d77b8c8dc1a4487891167ca8403f7244396a0dbe0f54b32fc3fab718372bfb",
    "USGS_INLAND_BATHY_V4_CROSSWALK/v4_to_nhd_spatial_crosswalk.csv": "747dcdda28535f83074aa486bdb01411e291f43733da8729cf418e62307a9a45",
    "TIGER_PR_BOUNDARY/tl_2025_us_state.zip": "59a220888a8d9be8117c4fcd38f542bd02d81abf0d198c78113595ad540dd957",
}


def reconstruct(root: Path, output: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f"snapshot root missing: {root}")

    sources = []
    for rel, expected in EXPECTED.items():
        path = root / rel
        if not path.is_file():
            raise RuntimeError(f"required historical byte missing: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"historical hash mismatch: {path} expected={expected} actual={actual}"
            )
        sources.append({
            "relative_path": rel,
            "bytes": path.stat().st_size,
            "sha256": actual,
            "binding_state": "EXACT_HASH_MATCH",
        })

    provenance_root = root / "provenance_manifests"
    manifests = []
    if not provenance_root.is_dir():
        raise RuntimeError(f"provenance manifest directory missing: {provenance_root}")
    for path in sorted(p for p in provenance_root.rglob("*") if p.is_file()):
        manifests.append({
            "relative_path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    if len(manifests) != 7:
        raise RuntimeError(f"expected 7 preserved provenance manifests, got {len(manifests)}")

    document = {
        "schema": "spiderweb.pr_hydrography.historical_snapshot_set.v0_2",
        "snapshot_set_id": "PR_HYDROGRAPHY_2026_08_11_v2",
        "as_of": "2026-08-11",
        "source_count": len(sources),
        "provenance_manifest_count": len(manifests),
        "sources": sources,
        "provenance_manifests": manifests,
        "raw_v4_archive_bound": True,
        "v4_crosswalk_preserved_as_derivative": True,
        "zero_silent_substitution": True,
        "canonical_history_superseded": False,
        "state": "PASS_2026_08_11_SNAPSHOT_SET_RECONSTRUCTED_WITH_RAW_V4",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != document:
            raise RuntimeError(f"refusing to overwrite non-identical snapshot-set manifest: {output}")
        return existing
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct the frozen 2026-08-11 PR hydrography snapshot set")
    parser.add_argument("--root", default="data/raw/pr_hydrography/historical_2026_08_11")
    parser.add_argument("--output", default="manifests/pr_hydrography/runtime/historical_snapshot_set_2026_08_11_v2.json")
    args = parser.parse_args()
    result = reconstruct(Path(args.root), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
