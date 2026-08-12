from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import sha256_file


def _canonicalize_entry(entry: dict, final_root: Path) -> dict:
    source_id = str(entry.get("source_id", ""))
    source_path = Path(str(entry.get("source_path", "")))
    if not source_id or not source_path.name:
        raise RuntimeError(f"invalid copied binding entry: {entry}")
    canonical = final_root / source_id / source_path.name
    if not canonical.is_file():
        raise RuntimeError(f"canonical migrated file missing: {canonical}")
    expected = str(entry.get("sha256", ""))
    actual = sha256_file(canonical)
    if expected and actual != expected:
        raise RuntimeError(f"canonical migrated hash mismatch: {canonical}: {actual} != {expected}")
    fixed = dict(entry)
    fixed["copied_path"] = str(canonical.resolve())
    fixed["post_promotion_sha256"] = actual
    fixed["post_promotion_verified"] = True
    return fixed


def _canonicalize_manifest_entry(entry: dict, final_root: Path, source_root: Path) -> dict:
    relative = Path(str(entry.get("relative_source_path", "")))
    if not relative.parts:
        raise RuntimeError(f"invalid manifest entry: {entry}")
    canonical = final_root / "provenance_manifests" / relative
    if not canonical.is_file():
        raise RuntimeError(f"canonical migrated manifest missing: {canonical}")
    expected = str(entry.get("sha256", ""))
    actual = sha256_file(canonical)
    if expected and actual != expected:
        raise RuntimeError(f"canonical manifest hash mismatch: {canonical}: {actual} != {expected}")
    source = source_root / relative
    if source.is_file() and sha256_file(source) != actual:
        raise RuntimeError(f"source/canonical manifest byte mismatch: {relative}")
    fixed = dict(entry)
    fixed["copied_path"] = str(canonical.resolve())
    fixed["post_promotion_sha256"] = actual
    fixed["post_promotion_verified"] = True
    return fixed


def repair(manifest_path: Path, final_root: Path) -> dict:
    manifest_path = manifest_path.expanduser().resolve()
    final_root = final_root.expanduser().resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("state") != "PASS_HISTORICAL_BYTES_AND_MANIFESTS_BOUND":
        raise RuntimeError(f"migration is not in PASS state: {data.get('state')}")
    source_root = Path(str(data["source_root"])).expanduser().resolve()
    copied_bindings = [_canonicalize_entry(row, final_root) for row in data.get("copied_bindings", [])]
    copied_manifests = [
        _canonicalize_manifest_entry(row, final_root, source_root)
        for row in data.get("copied_manifests", [])
    ]
    if len(copied_bindings) != 4:
        raise RuntimeError(f"expected four historical copied bindings; got {len(copied_bindings)}")
    if not copied_manifests:
        raise RuntimeError("expected preserved provenance manifests")
    data["destination"] = str(final_root)
    data["copied_bindings"] = copied_bindings
    data["copied_manifests"] = copied_manifests
    data["post_promotion_paths_canonical"] = True
    data["post_promotion_hash_verification"] = "PASS"
    data["staging_paths_retained_as_canonical"] = False
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(manifest_path)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonicalize and verify historical migration manifest paths after atomic promotion")
    parser.add_argument(
        "--manifest",
        default="manifests/pr_hydrography/runtime/historical_2026_08_11_migration.json",
    )
    parser.add_argument(
        "--final-root",
        default="data/raw/pr_hydrography/historical_2026_08_11",
    )
    args = parser.parse_args()
    result = repair(Path(args.manifest), Path(args.final_root))
    print(json.dumps({
        "state": result["state"],
        "post_promotion_paths_canonical": result["post_promotion_paths_canonical"],
        "post_promotion_hash_verification": result["post_promotion_hash_verification"],
        "copied_binding_count": len(result.get("copied_bindings", [])),
        "copied_manifest_count": len(result.get("copied_manifests", [])),
        "destination": result["destination"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
