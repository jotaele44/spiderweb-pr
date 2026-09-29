#!/usr/bin/env python3
"""Materialize and certify PR_GRID_GEOGRAPHIC_V2 RC1.

Writes complete CSV indexes for L0-L3 and a canonical release manifest. The
manifest hashes the frozen source contract and canonical schemas. Grid geometry
is generated entirely from the native EPSG:6566 numeric contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from spiderweb.geographic_grid_v2 import (
    CRS,
    EXTENT_X_MAX,
    EXTENT_X_MIN,
    EXTENT_Y_MAX,
    EXTENT_Y_MIN,
    GENERATOR_VERSION,
    GRID_ID,
    GRID_VERSION,
    LEVEL_ORDER,
    LEVELS,
    ORIGIN_X,
    ORIGIN_Y,
    canonical_json_bytes,
    manifest_sha256,
    write_level_csv,
)

SOURCE = REPO_ROOT / "registry/spatial/v2/pr_grid_geographic_v2.source.json"
CELL_SCHEMA = REPO_ROOT / "schemas/pr_grid_geographic_v2_cell.schema.json"
BINDING_SCHEMA = REPO_ROOT / "schemas/pr_grid_geographic_v2_binding.schema.json"
MASK_SCHEMA = REPO_ROOT / "schemas/pr_grid_geographic_v2_mask.schema.json"
MANIFEST_SCHEMA = REPO_ROOT / "schemas/pr_grid_geographic_v2_manifest.schema.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(level_artifacts: dict[str, dict[str, object]]) -> dict[str, object]:
    manifest: dict[str, object] = {
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "CRS": CRS,
        "Origin_X": ORIGIN_X,
        "Origin_Y": ORIGIN_Y,
        "Extent_XMin": EXTENT_X_MIN,
        "Extent_YMin": EXTENT_Y_MIN,
        "Extent_XMax": EXTENT_X_MAX,
        "Extent_YMax": EXTENT_Y_MAX,
        "Row_Direction": "SOUTH_TO_NORTH",
        "Column_Direction": "WEST_TO_EAST",
        "Full_Cell_Policy": "FULL_SQUARE",
        "Levels": {
            level: {
                "resolution_m": LEVELS[level].resolution_m,
                "rows": LEVELS[level].rows,
                "columns": LEVELS[level].columns,
                "cell_count": LEVELS[level].cell_count,
                **level_artifacts.get(level, {}),
            }
            for level in LEVEL_ORDER
        },
        "Cell_ID_Format": "PRG2:<LEVEL>:R<row:03d>:C<column:04d>",
        "Boundary_Semantics_Version": "pr-grid-v2-boundary/1.0",
        "Binding_Schema_Version": "pr-grid-v2-binding/1.0",
        "Mask_Schema_Version": "pr-grid-v2-mask/1.0",
        "Geometry_Generator_Version": GENERATOR_VERSION,
        "Release_State": "RC1_CANDIDATE",
        "Source_Manifest_SHA256": file_sha256(SOURCE),
        "Cell_Schema_SHA256": file_sha256(CELL_SCHEMA),
        "Binding_Schema_SHA256": file_sha256(BINDING_SCHEMA),
        "Mask_Schema_SHA256": file_sha256(MASK_SCHEMA),
        "Manifest_Schema_SHA256": file_sha256(MANIFEST_SCHEMA),
        "Grid_Manifest_SHA256": "",
    }
    manifest["Grid_Manifest_SHA256"] = manifest_sha256(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "registry/spatial/v2/generated",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "registry/spatial/v2/pr_grid_geographic_v2.manifest.json",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="compute manifest without materializing CSV indexes",
    )
    args = parser.parse_args()

    artifacts: dict[str, dict[str, object]] = {}
    if not args.manifest_only:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for level in LEVEL_ORDER:
            path = args.output_dir / f"pr_grid_geographic_v2_{level.lower()}.csv"
            count, digest = write_level_csv(level, path)
            expected = LEVELS[level].cell_count
            if count != expected:
                raise SystemExit(f"{level}: {count} rows != expected {expected}")
            artifacts[level] = {
                "artifact_path": str(path.resolve().relative_to(REPO_ROOT)),
                "artifact_sha256": digest,
            }

    manifest = build_manifest(artifacts)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_bytes(canonical_json_bytes(manifest))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
