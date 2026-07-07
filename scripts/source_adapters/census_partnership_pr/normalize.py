"""Normalize downloaded Census Partnership ZIP payloads into GeoPackage.

This module intentionally shells out to GDAL/OGR when promotion is requested. Raw
ZIPs and extracted shapefile trees remain runtime-only artifacts under the source
adapter policy.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def extract_zip(zip_path: Path, extract_root: Path) -> Path:
    """Extract a ZIP into a deterministic runtime directory."""

    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Not a ZIP archive: {zip_path}")
    destination = extract_root / zip_path.stem
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)
    return destination


def extract_nested_zips(root: Path) -> list[Path]:
    """Recursively extract nested ZIP files under an extracted Census bundle.

    The Census batch endpoint can return an outer ZIP containing one ZIP per
    municipio. This function walks newly extracted directories until no nested
    ZIP remains unexpanded. Each nested archive is extracted beside itself into a
    sibling directory named after the archive stem.
    """

    extracted_dirs: list[Path] = []
    seen: set[Path] = set()

    while True:
        nested = [path for path in sorted(root.rglob("*.zip")) if path.resolve() not in seen]
        if not nested:
            return extracted_dirs
        for zip_path in nested:
            seen.add(zip_path.resolve())
            if not zipfile.is_zipfile(zip_path):
                continue
            destination = zip_path.with_suffix("")
            destination.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(destination)
            extracted_dirs.append(destination)


def extract_zip_tree(zip_path: Path, extract_root: Path) -> Path:
    """Extract an outer ZIP and any nested ZIPs it contains."""

    extracted = extract_zip(zip_path, extract_root)
    extract_nested_zips(extracted)
    return extracted


def find_vector_inputs(extracted_dir: Path) -> list[Path]:
    """Return shapefile inputs found in an extracted Census bundle."""

    return sorted(extracted_dir.rglob("*.shp"))


def normalize_zip_to_gpkg(zip_path: Path, output_gpkg: Path, extract_root: Path | None = None) -> Path:
    """Convert all shapefiles inside a ZIP into a single GeoPackage.

    Requires `ogr2ogr` to be available locally. This keeps heavy GIS dependencies
    out of CI and avoids storing raw or extracted Census payloads in git.
    """

    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise RuntimeError("ogr2ogr is required for GeoPackage normalization")

    if extract_root is None:
        with tempfile.TemporaryDirectory(prefix="census_partnership_pr_") as tmpdir:
            return _normalize_from_extracted(zip_path, output_gpkg, Path(tmpdir), ogr2ogr)
    return _normalize_from_extracted(zip_path, output_gpkg, extract_root, ogr2ogr)


def _normalize_from_extracted(zip_path: Path, output_gpkg: Path, extract_root: Path, ogr2ogr: str) -> Path:
    extracted = extract_zip_tree(zip_path, extract_root)
    shapefiles = find_vector_inputs(extracted)
    if not shapefiles:
        raise ValueError(f"No shapefiles found in {zip_path}")

    output_gpkg.parent.mkdir(parents=True, exist_ok=True)
    if output_gpkg.exists():
        output_gpkg.unlink()

    for index, shp in enumerate(shapefiles):
        command = [ogr2ogr, "-f", "GPKG", str(output_gpkg), str(shp)]
        if index > 0:
            command.insert(3, "-append")
        subprocess.run(command, check=True)  # noqa: S603 - fixed executable resolved by shutil.which
    return output_gpkg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize a Census Partnership ZIP to GeoPackage")
    parser.add_argument("zip_path")
    parser.add_argument("output_gpkg")
    parser.add_argument("--extract-root", default="data/extracted/census_partnership_pr")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    normalize_zip_to_gpkg(Path(args.zip_path), Path(args.output_gpkg), Path(args.extract_root))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
