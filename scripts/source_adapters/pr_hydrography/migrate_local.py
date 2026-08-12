from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .control_plane import bind_historical_file
from .core import sha256_file

KNOWN_INPUTS = {
    "USGS_NHD_WATERBODY": {
        "relative_path": "_DENOMINATOR/NHD_PR_2026_08_11/nhd_pr_lakepond_reservoir.gpkg",
        "sha256": "08a216d247a1ed7a59046d94a4a8f858ffbd9e9164175ce8927ccd8e791cc45a",
        "original_certification": "NHD_PR_2026_08_11",
    },
    "USACE_NID_DAMS": {
        "relative_path": "_DENOMINATOR/nid_nation.csv",
        "sha256": "67890b6bc0eca8976fa646080bc527a619b8729166dcf7bf7ec694db1bb3f82e",
        "original_certification": "NID_PR_2026_08_11",
    },
    "USGS_INLAND_BATHY_V4_CROSSWALK": {
        "relative_path": "_DENOMINATOR/NHD_PR_2026_08_11/v4_to_nhd_spatial_crosswalk.csv",
        "sha256": "747dcdda28535f83074aa486bdb01411e291f43733da8729cf418e62307a9a45",
        "original_certification": "V4_TO_NHD_2026_08_11",
    },
}

TIGER_PATTERNS = (
    "_DENOMINATOR/NHD_PR_2026_08_11/boundary/tl_2025_us_state.zip",
    "_DENOMINATOR/NHD_PR_2026_08_11/boundary/*boundary*.gpkg",
    "_DENOMINATOR/NHD_PR_2026_08_11/boundary/*boundary*.geojson",
    "_DENOMINATOR/NHD_PR_2026_08_11/boundary/*state*.gpkg",
    "_DENOMINATOR/NHD_PR_2026_08_11/boundary/*state*.geojson",
)

MANIFEST_PATTERNS = (
    "_DENOMINATOR/NHD_PR_2026_08_11/*certification*.json",
    "_DENOMINATOR/NHD_PR_2026_08_11/*CERTIFICATION*.json",
    "_DENOMINATOR/NHD_PR_2026_08_11/*SHA256SUMS*.txt",
    "_DENOMINATOR/NHD_PR_2026_08_11/*manifest*.json",
)


def _media(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def discover(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    rows = []
    for source_id, spec in KNOWN_INPUTS.items():
        path = root / spec["relative_path"]
        rows.append({
            "source_id": source_id,
            "path": str(path),
            "exists": path.is_file(),
            "expected_sha256": spec["sha256"],
            "actual_sha256": sha256_file(path) if path.is_file() else "",
            "original_certification": spec["original_certification"],
            "media_type": _media(path),
        })

    tiger_candidates = sorted({path for pattern in TIGER_PATTERNS for path in root.glob(pattern) if path.is_file()})
    manifests = sorted({path for pattern in MANIFEST_PATTERNS for path in root.glob(pattern) if path.is_file()})
    return {
        "root": str(root),
        "known_inputs": rows,
        "tiger_candidates": [str(path) for path in tiger_candidates],
        "relevant_manifests": [str(path) for path in manifests],
    }


def _copy_verified(source: Path, target: Path, expected_sha256: str) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    actual = sha256_file(target)
    if actual != expected_sha256:
        raise RuntimeError(
            f"post-copy hash mismatch: {target}; expected={expected_sha256}; actual={actual}"
        )
    return {
        "source_path": str(source),
        "copied_path": str(target),
        "bytes": target.stat().st_size,
        "sha256": actual,
        "media_type": _media(source),
    }


def migrate(
    root: Path,
    snapshot_root: Path,
    manifest_output: Path,
    *,
    tiger_path: Path | None = None,
    tiger_expected_sha256: str = "",
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    discovery = discover(root)
    bindings = []

    for source_id, spec in KNOWN_INPUTS.items():
        path = root / spec["relative_path"]
        record = bind_historical_file(
            path,
            source_id=source_id,
            expected_sha256=spec["sha256"],
            media_type=_media(path),
            original_certification=spec["original_certification"],
        )
        bindings.append(asdict(record))

    if any(row["binding_state"] != "EXACT_HASH_MATCH" for row in bindings):
        raise RuntimeError("historical migration blocked: one or more frozen hashes do not match")

    if tiger_path is None:
        raise RuntimeError("historical migration requires TIGER source binding; use --tiger-path")
    tiger_path = Path(tiger_path).expanduser().resolve()
    if not tiger_expected_sha256:
        raise RuntimeError("TIGER migration requires --tiger-expected-sha256; no silent trust-on-first-use")

    tiger_binding = asdict(
        bind_historical_file(
            tiger_path,
            source_id="TIGER_PR_BOUNDARY",
            expected_sha256=tiger_expected_sha256,
            media_type=_media(tiger_path),
            original_certification="TIGER_PR_BOUNDARY_2026_08_11",
        )
    )
    if tiger_binding["binding_state"] != "EXACT_HASH_MATCH":
        raise RuntimeError("historical migration blocked: TIGER hash mismatch")

    manifest_sources = [Path(path) for path in discovery["relevant_manifests"]]
    if not manifest_sources:
        raise RuntimeError("historical migration blocked: no certification/SHA manifests discovered")

    snapshot_root = Path(snapshot_root)
    migration_root = snapshot_root / "historical_2026_08_11"
    if migration_root.exists():
        raise FileExistsError(f"historical migration destination already exists: {migration_root}")

    snapshot_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".historical_2026_08_11-", dir=snapshot_root))

    copied_bindings: list[dict[str, Any]] = []
    copied_manifests: list[dict[str, Any]] = []
    try:
        for row in bindings + [tiger_binding]:
            source = Path(row["source_path"])
            target_dir = staging / row["source_id"]
            target = target_dir / source.name
            copied = _copy_verified(source, target, row["sha256"])
            copied.update({
                "source_id": row["source_id"],
                "original_certification": row["original_certification"],
                "binding_state": row["binding_state"],
            })
            copied_bindings.append(copied)
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "binding.json").write_text(
                json.dumps(row, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        manifest_root = staging / "provenance_manifests"
        for source in manifest_sources:
            relative = source.relative_to(root)
            target = manifest_root / relative
            digest = sha256_file(source)
            copied = _copy_verified(source, target, digest)
            copied["relative_source_path"] = str(relative)
            copied_manifests.append(copied)

        migration_manifest = {
            "schema": "spiderweb.pr_hydrography.historical_migration.v0_2",
            "source_root": str(root),
            "destination": str(migration_root),
            "bindings": bindings,
            "tiger_binding": tiger_binding,
            "copied_bindings": copied_bindings,
            "copied_manifests": copied_manifests,
            "discovery": discovery,
            "historical_bytes_reencoded": False,
            "manifest_bytes_reencoded": False,
            "canonical_history_superseded": False,
            "state": "PASS_HISTORICAL_BYTES_AND_MANIFESTS_BOUND",
        }
        (staging / "migration_manifest.json").write_text(
            json.dumps(migration_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        staging.replace(migration_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    manifest_output = Path(manifest_output)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(migration_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return migration_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind certified PR_RESERVOIR_DATA bytes and provenance manifests into Spiderweb historical snapshot storage"
    )
    parser.add_argument("root", nargs="?", default="/Users/jotaele/Downloads/PR_RESERVOIR_DATA")
    parser.add_argument("--snapshot-root", default="data/raw/pr_hydrography")
    parser.add_argument(
        "--manifest-output",
        default="manifests/pr_hydrography/runtime/historical_2026_08_11_migration.json",
    )
    parser.add_argument("--tiger-path")
    parser.add_argument("--tiger-expected-sha256", default="")
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()

    if args.discover_only:
        print(json.dumps(discover(Path(args.root)), indent=2, ensure_ascii=False))
        return 0

    result = migrate(
        Path(args.root),
        Path(args.snapshot_root),
        Path(args.manifest_output),
        tiger_path=Path(args.tiger_path) if args.tiger_path else None,
        tiger_expected_sha256=args.tiger_expected_sha256,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["state"] == "PASS_HISTORICAL_BYTES_AND_MANIFESTS_BOUND" else 6


if __name__ == "__main__":
    raise SystemExit(main())
