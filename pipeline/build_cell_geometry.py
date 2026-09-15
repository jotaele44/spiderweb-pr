#!/usr/bin/env python3
"""Materialise the geographic geometry layer for the canonical federation grid.

The frozen grid CSV is a logical index. This builder projects every one of its
98,304 cells through the certified transform and emits the geographic layer plus
a manifest carrying the cardinality and content hash.

The geometry itself is a *build product*, not committed source: the grid is a
regular lattice, so every polygon is derivable from the transform and the cell's
row/column. Committing ~30 MB of derivable polygons would violate the
repository's data policy for no gain. What is committed is the manifest and its
hash, which lets CI regenerate the layer and prove it is byte-identical.

Cardinality is an invariant, not a statistic: exactly 98,304 geometries, one per
Cell_ID, no orphans and no duplicates. Classification never gates existence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from federation.spatial_resolver import (  # noqa: E402
    CELL_COUNT,
    GRID_COLUMNS,
    GRID_ROWS,
    GridTransform,
    cell_id,
)

GRID_CSV = REPO_ROOT / "registry/spatial/pr_grid_full_cell_index_saturated.csv"
GEOMETRY_DIR = REPO_ROOT / "registry/spatial/geometry"
GEOMETRY_PATH = GEOMETRY_DIR / "pr_grid_cell_geometry.geojsonl"
MANIFEST_PATH = GEOMETRY_DIR / "pr_grid_geometry_manifest.json"
SHA_PATH = GEOMETRY_DIR / "pr_grid_geometry_sha256.txt"

EARTH_RADIUS_M = 6_378_137.0


def cell_area_m2(west: float, south: float, east: float, north: float) -> float:
    """Spherical quadrangle area. Cells are small, so a sphere is ample here."""
    lon_span = math.radians(east - west)
    return abs(
        EARTH_RADIUS_M
        * EARTH_RADIUS_M
        * lon_span
        * (math.sin(math.radians(north)) - math.sin(math.radians(south)))
    )


def iter_geometry(transform: GridTransform, classifications: dict[str, str]) -> Iterator[dict]:
    for row_index in range(GRID_ROWS):
        for column_index in range(GRID_COLUMNS):
            identifier = cell_id(row_index, column_index)
            west, south, east, north = transform.cell_bounds(row_index, column_index)
            ring = [
                [round(west, 8), round(south, 8)],
                [round(east, 8), round(south, 8)],
                [round(east, 8), round(north, 8)],
                [round(west, 8), round(north, 8)],
                [round(west, 8), round(south, 8)],
            ]
            geometry = {"type": "Polygon", "coordinates": [ring]}
            geometry_sha256 = hashlib.sha256(
                json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            yield {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "Cell_ID": identifier,
                    "Row_Index": row_index,
                    "Column_Index": column_index,
                    "Grid_Version": transform.grid_version,
                    "Geometry_Version": transform.geometry_version,
                    "BBox_WGS84": [round(west, 8), round(south, 8), round(east, 8), round(north, 8)],
                    "Centroid_Lon": round((west + east) / 2.0, 8),
                    "Centroid_Lat": round((south + north) / 2.0, 8),
                    "Area_m2": round(cell_area_m2(west, south, east, north), 3),
                    "Geometry_SHA256": geometry_sha256,
                    "Classification": classifications.get(identifier, "Water_or_Empty"),
                    "Certification_State": transform.certification_state,
                },
            }


def load_classifications(path: Path = GRID_CSV) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["Cell_ID"]: row["Classification"] for row in csv.DictReader(handle)}


def build(output: Path = GEOMETRY_PATH, *, write: bool = True) -> dict[str, object]:
    transform = GridTransform.load()
    classifications = load_classifications()

    seen: set[str] = set()
    digest = hashlib.sha256()
    written = 0
    handle = output.open("w", encoding="utf-8") if write else None
    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for feature in iter_geometry(transform, classifications):
            identifier = feature["properties"]["Cell_ID"]
            if identifier in seen:
                raise SystemExit(f"duplicate Cell_ID emitted: {identifier}")
            seen.add(identifier)
            line = json.dumps(feature, sort_keys=True, separators=(",", ":")) + "\n"
            digest.update(line.encode("utf-8"))
            if handle is not None:
                handle.write(line)
            written += 1
    finally:
        if handle is not None:
            handle.close()

    orphans = sorted(seen - set(classifications))
    missing = sorted(set(classifications) - seen)
    if written != CELL_COUNT or orphans or missing:
        raise SystemExit(
            f"geometry cardinality broken: wrote {written} (expected {CELL_COUNT}), "
            f"{len(orphans)} orphan, {len(missing)} missing"
        )

    return {
        "dataset": "pr_grid_cell_geometry",
        "path": str(output.relative_to(REPO_ROOT)),
        "format": "geojsonl",
        "geometry_version": transform.geometry_version,
        "grid_version": transform.grid_version,
        "certification_state": transform.certification_state,
        "cell_count": written,
        "grid": {"rows": GRID_ROWS, "columns": GRID_COLUMNS},
        "duplicate_cell_ids": 0,
        "orphan_geometries": 0,
        "missing_geometries": 0,
        "sha256": digest.hexdigest(),
        "size_bytes": output.stat().st_size if write and output.exists() else None,
        "crs": "EPSG:4326",
        "derivable": True,
        "derivable_note": (
            "Regenerate with `python -m pipeline.build_cell_geometry`. The layer is a "
            "deterministic function of the transform record and the frozen grid, so CI "
            "rebuilds it and compares sha256 rather than tracking the bytes."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true", help="build and check invariants only")
    parser.add_argument("--output", type=Path, default=GEOMETRY_PATH)
    args = parser.parse_args(argv)

    manifest = build(args.output, write=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    SHA_PATH.write_text(f"{manifest['sha256']}  {manifest['path']}\n", encoding="utf-8")

    print(f"cells={manifest['cell_count']} (expected {CELL_COUNT})")
    print(f"duplicates=0 orphans=0 missing=0")
    print(f"sha256={manifest['sha256']}")
    print(f"certification_state={manifest['certification_state']}")
    size = manifest["size_bytes"]
    if size:
        print(f"size={size/1_048_576:.1f} MiB (build product, not tracked)")
    if args.validate:
        args.output.unlink(missing_ok=True)
        print("validated; geometry removed (--validate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
