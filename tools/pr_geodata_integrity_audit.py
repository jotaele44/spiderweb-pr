#!/usr/bin/env python3
"""
PR Geodata Integrity Audit

Purpose
-------
Pre-flight verification for the Puerto Rico ILAP DEM / geometry anomaly workflow.

This script checks whether a local PR_Geodata folder is safe to use before running
DEM anomaly extraction or ILAP scoring. It is intentionally conservative: if a
check cannot be completed because optional GIS libraries are missing, it emits a
WARN rather than inventing a PASS.

Core checks
-----------
1. DEM tile count, zero-byte files, total size, CRS/resolution inventory.
2. Shapefile sidecar integrity: .shp + .shx + .dbf + .prj.
3. TIGER/GPKG/GDB existence and readability where optional GIS tooling exists.
4. Pipeline path references in the repo, including stale path detection.
5. Final GO / CONDITIONAL_GO / NO_GO status for the ILAP DEM pilot.

Optional dependencies
---------------------
- rasterio: reads GeoTIFF CRS/resolution/shape.
- fiona or pyogrio: lists layers in GPKG/GDB vector containers.
- gdalinfo / ogrinfo CLI: used as fallbacks if installed.

The script still runs with only the Python standard library, but CRS and vector
container readability checks will be WARN-only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_EXPECTED_DEM_COUNT = 191
DEFAULT_OUTPUT_DIR = Path("outputs") / "pr_geodata_audit"

EXPECTED_CORE_DIRS = {
    "dem": "01_DEM_1m_LiDAR",
    "geodatabases": "03_Geodatabases",
    "shapefiles": "05_Vector_Shapefiles",
}

EXPECTED_DEM_CRS = {"EPSG:26919", "EPSG:26920"}

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".bat",
    ".ps1",
}

EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "outputs",
    "output",
    "data",
    "Data",
    "PR_Geodata",
}

STALE_PATH_MARKERS = [
    "Geometry/Elevation & Terrain/3DEP_Download/tiles",
    "Geometry\\Elevation & Terrain\\3DEP_Download\\tiles",
    "3DEP_Download/tiles",
    "3DEP_Download\\tiles",
    "ICAP/Datos",
    "ICAP\\Datos",
    "Documents/Data/Geometry",
    "Documents\\Data\\Geometry",
]

EXPECTED_PATH_MARKERS = [
    "PR_Geodata/01_DEM_1m_LiDAR",
    "PR_Geodata\\01_DEM_1m_LiDAR",
    "01_DEM_1m_LiDAR",
]

ROAD_LAYER_MARKERS = [
    "edge",
    "edges",
    "road",
    "roads",
    "prisecroads",
    "primaryroads",
    "secondaryroads",
]


@dataclass
class Finding:
    severity: str
    category: str
    check: str
    message: str
    path: str = ""
    evidence: str = ""


class Audit:
    def __init__(self) -> None:
        self.findings: List[Finding] = []
        self.metrics: Dict[str, Any] = {}

    def add(
        self,
        severity: str,
        category: str,
        check: str,
        message: str,
        path: Path | str | None = None,
        evidence: Any = "",
    ) -> None:
        severity = severity.upper()
        if severity not in {"PASS", "WARN", "FAIL", "INFO"}:
            raise ValueError(f"Invalid severity: {severity}")
        if isinstance(evidence, (dict, list, tuple)):
            evidence_text = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        else:
            evidence_text = "" if evidence is None else str(evidence)
        self.findings.append(
            Finding(
                severity=severity,
                category=category,
                check=check,
                message=message,
                path=str(path or ""),
                evidence=evidence_text,
            )
        )

    def severity_counts(self) -> Dict[str, int]:
        return dict(Counter(f.severity for f in self.findings))

    def gate_status(self, strict: bool = False) -> str:
        counts = self.severity_counts()
        if counts.get("FAIL", 0) > 0:
            return "NO_GO"
        if strict and counts.get("WARN", 0) > 0:
            return "NO_GO"
        if counts.get("WARN", 0) > 0:
            return "CONDITIONAL_GO"
        return "GO"


def human_bytes(value: int | float) -> str:
    value = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def discover_geodata_root(input_path: Optional[str]) -> Path:
    if input_path:
        return Path(input_path).expanduser().resolve()

    cwd = Path.cwd().resolve()
    if cwd.name == "PR_Geodata":
        return cwd

    candidate = cwd / "PR_Geodata"
    if candidate.exists():
        return candidate.resolve()

    for probe in [
        Path.home() / "Documents" / "Data" / "PR_Geodata",
        Path.home() / "Data" / "PR_Geodata",
        Path.home() / "PR_Geodata",
    ]:
        if probe.exists():
            return probe.resolve()

    return candidate.resolve()


def find_first_existing(root: Path, preferred_name: str, fallback_globs: Sequence[str]) -> Optional[Path]:
    direct = root / preferred_name
    if direct.exists():
        return direct

    for pattern in fallback_globs:
        matches = sorted([p for p in root.rglob(pattern) if p.exists()])
        if matches:
            return matches[0]

    return None


def import_optional(module_name: str) -> Tuple[Optional[Any], Optional[str]]:
    try:
        module = __import__(module_name)
        return module, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def run_json_command(command: Sequence[str], timeout: int = 30) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        proc = subprocess.run(
            list(command),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    if proc.returncode != 0:
        return None, proc.stderr.strip() or proc.stdout.strip()

    try:
        return json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return None, f"JSONDecodeError: {exc}; stderr={proc.stderr.strip()}"


def audit_root_structure(audit: Audit, geodata_root: Path) -> Dict[str, Optional[Path]]:
    audit.metrics["geodata_root"] = str(geodata_root)

    if not geodata_root.exists():
        audit.add("FAIL", "root", "geodata_root_exists", "PR_Geodata root does not exist.", geodata_root)
        return {"dem": None, "geodatabases": None, "shapefiles": None}

    if not geodata_root.is_dir():
        audit.add("FAIL", "root", "geodata_root_is_directory", "PR_Geodata path exists but is not a directory.", geodata_root)
        return {"dem": None, "geodatabases": None, "shapefiles": None}

    audit.add("PASS", "root", "geodata_root_exists", "PR_Geodata root exists and is a directory.", geodata_root)

    resolved = {
        "dem": find_first_existing(geodata_root, EXPECTED_CORE_DIRS["dem"], ["*DEM*LiDAR*", "*DEM*", "*3DEP*"]),
        "geodatabases": find_first_existing(geodata_root, EXPECTED_CORE_DIRS["geodatabases"], ["*Geodatabase*", "*Geodatabases*", "*.gdb"]),
        "shapefiles": find_first_existing(geodata_root, EXPECTED_CORE_DIRS["shapefiles"], ["*Shapefile*", "*Shapefiles*", "*.shp"]),
    }

    for key, expected_name in EXPECTED_CORE_DIRS.items():
        path = resolved[key]
        if path is None:
            audit.add(
                "FAIL",
                "root",
                f"{key}_directory_found",
                f"Expected core directory or equivalent dataset group was not found: {expected_name}",
                geodata_root,
            )
        else:
            audit.add("PASS", "root", f"{key}_directory_found", f"Located {key} directory/dataset group.", path, safe_rel(path, geodata_root))

    return resolved


def audit_dem(
    audit: Audit,
    geodata_root: Path,
    dem_dir: Optional[Path],
    expected_count: int,
    sample_limit: int,
    all_dem_crs: bool,
    no_raster_read: bool,
) -> List[Path]:
    if dem_dir is None or not dem_dir.exists():
        audit.add("FAIL", "dem", "dem_directory_exists", "DEM directory was not found; cannot validate LiDAR tiles.", dem_dir or "")
        audit.metrics["dem"] = {"tile_count": 0}
        return []

    dem_tiles = sorted(
        p for p in dem_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in {".tif", ".tiff"}
        and not p.name.lower().endswith((".ovr", ".aux.xml"))
    )
    zip_files = sorted(p for p in dem_dir.rglob("*.zip") if p.is_file())
    zero_byte = [p for p in dem_tiles if p.stat().st_size == 0]
    total_size = sum(p.stat().st_size for p in dem_tiles)

    audit.metrics["dem"] = {
        "directory": str(dem_dir),
        "tile_count": len(dem_tiles),
        "expected_tile_count": expected_count,
        "total_size_bytes": total_size,
        "total_size_human": human_bytes(total_size),
        "zero_byte_count": len(zero_byte),
        "zip_count_inside_dem_dir": len(zip_files),
    }

    if len(dem_tiles) == expected_count:
        audit.add("PASS", "dem", "tile_count", f"DEM tile count matches expected count: {expected_count}.", dem_dir)
    elif len(dem_tiles) < expected_count:
        audit.add("FAIL", "dem", "tile_count", f"DEM tile count is below expected count: found {len(dem_tiles)}, expected {expected_count}.", dem_dir)
    else:
        audit.add("WARN", "dem", "tile_count", f"DEM tile count is above expected count: found {len(dem_tiles)}, expected {expected_count}. Check for duplicates.", dem_dir)

    if zero_byte:
        audit.add("FAIL", "dem", "zero_byte_tiles", f"Found {len(zero_byte)} zero-byte DEM tile(s).", zero_byte[0], [safe_rel(p, geodata_root) for p in zero_byte[:20]])
    else:
        audit.add("PASS", "dem", "zero_byte_tiles", "No zero-byte DEM tiles found.", dem_dir)

    if total_size < 30 * 1024**3 and expected_count >= 100:
        audit.add("WARN", "dem", "total_size", f"DEM total size is {human_bytes(total_size)}, lower than expected for the known ~44 GB set.", dem_dir)
    else:
        audit.add("PASS", "dem", "total_size", f"DEM total size is {human_bytes(total_size)}.", dem_dir)

    if zip_files:
        audit.add("INFO", "dem", "zip_files_present", f"Found {len(zip_files)} ZIP file(s) inside the DEM directory. The main DEM tiles should be plain GeoTIFFs; ZIPs may be auxiliary datasets.", zip_files[0], [safe_rel(p, geodata_root) for p in zip_files[:20]])

    audit_dem_crs(audit, geodata_root, dem_tiles, sample_limit, all_dem_crs, no_raster_read)
    return dem_tiles


def audit_dem_crs(
    audit: Audit,
    geodata_root: Path,
    dem_tiles: List[Path],
    sample_limit: int,
    all_dem_crs: bool,
    no_raster_read: bool,
) -> None:
    if not dem_tiles:
        return

    if no_raster_read:
        audit.add("WARN", "dem", "crs_inventory", "Raster read disabled by --no-raster-read; CRS/resolution not verified.")
        return

    sample_tiles = dem_tiles if all_dem_crs else dem_tiles[: max(1, min(sample_limit, len(dem_tiles)))]
    audit.metrics["dem"]["crs_sample_count"] = len(sample_tiles)
    rasterio, rasterio_error = import_optional("rasterio")

    crs_counter: Counter[str] = Counter()
    resolution_counter: Counter[str] = Counter()
    shape_counter: Counter[str] = Counter()
    read_errors: List[str] = []

    if rasterio is not None:
        for tile in sample_tiles:
            try:
                with rasterio.open(tile) as src:
                    crs = src.crs.to_string() if src.crs else "UNKNOWN"
                    crs_counter[crs] += 1
                    resolution_counter[f"{src.res[0]:.6g} x {src.res[1]:.6g}"] += 1
                    shape_counter[f"{src.width} x {src.height}"] += 1
            except Exception as exc:
                read_errors.append(f"{safe_rel(tile, geodata_root)} :: {type(exc).__name__}: {exc}")

        audit.metrics["dem"]["crs_counts"] = dict(crs_counter)
        audit.metrics["dem"]["resolution_counts"] = dict(resolution_counter)
        audit.metrics["dem"]["shape_counts"] = dict(shape_counter)
        audit.metrics["dem"]["raster_read_errors"] = read_errors[:50]

        if read_errors:
            audit.add("FAIL", "dem", "crs_inventory", f"Rasterio failed to read {len(read_errors)} sampled DEM tile(s).", evidence=read_errors[:10])
            return

        unexpected = sorted(set(crs_counter) - EXPECTED_DEM_CRS)
        if unexpected:
            audit.add("WARN", "dem", "crs_inventory", "Sampled DEM CRS inventory contains CRS values outside expected Puerto Rico UTM zones.", evidence={"crs_counts": dict(crs_counter), "expected": sorted(EXPECTED_DEM_CRS)})
        else:
            audit.add("PASS", "dem", "crs_inventory", "Sampled DEM CRS values are within expected Puerto Rico UTM zones.", evidence={"crs_counts": dict(crs_counter), "sample_count": len(sample_tiles)})

        if any(not key.startswith("1") for key in resolution_counter.keys()):
            audit.add("WARN", "dem", "resolution_inventory", "Sampled DEM resolutions are not uniformly 1-meter-like.", evidence=dict(resolution_counter))
        else:
            audit.add("PASS", "dem", "resolution_inventory", "Sampled DEM resolutions are consistent with 1-meter tiles.", evidence=dict(resolution_counter))
        return

    gdalinfo = shutil.which("gdalinfo")
    if gdalinfo:
        for tile in sample_tiles:
            payload, error = run_json_command([gdalinfo, "-json", str(tile)], timeout=30)
            if payload is None:
                read_errors.append(f"{safe_rel(tile, geodata_root)} :: {error}")
                continue

            coordinate_system = payload.get("coordinateSystem", {})
            if "EPSG" in json.dumps(coordinate_system):
                crs_counter["GDAL_READ_CRS_PRESENT"] += 1
            else:
                crs_counter["UNKNOWN"] += 1

            size = payload.get("size", [])
            if len(size) >= 2:
                shape_counter[f"{size[0]} x {size[1]}"] += 1

            geo_transform = payload.get("geoTransform", [])
            if len(geo_transform) >= 6:
                resolution_counter[f"{abs(geo_transform[1]):.6g} x {abs(geo_transform[5]):.6g}"] += 1

        audit.metrics["dem"]["crs_counts"] = dict(crs_counter)
        audit.metrics["dem"]["resolution_counts"] = dict(resolution_counter)
        audit.metrics["dem"]["shape_counts"] = dict(shape_counter)
        audit.metrics["dem"]["raster_read_errors"] = read_errors[:50]

        if read_errors:
            audit.add("FAIL", "dem", "crs_inventory", f"gdalinfo failed to read {len(read_errors)} sampled DEM tile(s).", evidence=read_errors[:10])
        else:
            audit.add("WARN", "dem", "crs_inventory", "gdalinfo could read sampled DEM tiles, but exact EPSG normalization requires rasterio for this audit.", evidence={"crs_counts": dict(crs_counter), "sample_count": len(sample_tiles)})
        return

    audit.add("WARN", "dem", "crs_inventory", "CRS/resolution not verified because neither rasterio nor gdalinfo is available.", evidence=rasterio_error or "rasterio import failed")


def primary_for_sidecar(path: Path) -> Optional[Path]:
    name = path.name
    suffix = path.suffix.lower()

    if name.lower().endswith(".shp.iso.xml"):
        return path.with_name(name[:-len(".shp.iso.xml")] + ".shp")
    if name.lower().endswith(".shp.xml"):
        return path.with_name(name[:-len(".shp.xml")] + ".shp")
    if suffix in {".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".fix"}:
        return path.with_suffix(".shp")
    return None


def audit_shapefiles(audit: Audit, geodata_root: Path, shapefile_dir: Optional[Path]) -> List[Path]:
    search_root = shapefile_dir if shapefile_dir and shapefile_dir.exists() else geodata_root
    shapefiles = sorted(p for p in search_root.rglob("*.shp") if p.is_file())

    audit.metrics["shapefiles"] = {"search_root": str(search_root), "count": len(shapefiles)}

    if not shapefiles:
        audit.add("FAIL", "shapefiles", "shapefile_count", "No .shp files found in the shapefile directory/root.", search_root)
        return []

    audit.add("PASS", "shapefiles", "shapefile_count", f"Found {len(shapefiles)} shapefile primary file(s).", search_root)

    required = [".shx", ".dbf", ".prj"]
    missing_by_shp: Dict[str, List[str]] = {}
    optional_missing_cpg: List[str] = []

    for shp in shapefiles:
        missing = [ext for ext in required if not shp.with_suffix(ext).exists()]
        if missing:
            missing_by_shp[safe_rel(shp, geodata_root)] = missing
        if not shp.with_suffix(".cpg").exists():
            optional_missing_cpg.append(safe_rel(shp, geodata_root))

    audit.metrics["shapefiles"]["missing_required_sidecar_count"] = len(missing_by_shp)
    audit.metrics["shapefiles"]["missing_cpg_count"] = len(optional_missing_cpg)

    if missing_by_shp:
        audit.add("FAIL", "shapefiles", "required_sidecars", f"{len(missing_by_shp)} shapefile(s) are missing required sidecar(s).", evidence=missing_by_shp)
    else:
        audit.add("PASS", "shapefiles", "required_sidecars", "All shapefiles have required .shx, .dbf, and .prj sidecars.", search_root)

    if optional_missing_cpg:
        audit.add("INFO", "shapefiles", "optional_cpg", f"{len(optional_missing_cpg)} shapefile(s) do not have .cpg encoding files. This is not fatal, but encoding may be ambiguous.", evidence=optional_missing_cpg[:25])

    sidecar_exts = {".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".fix"}
    sidecars = [
        p for p in search_root.rglob("*")
        if p.is_file()
        and (p.suffix.lower() in sidecar_exts or p.name.lower().endswith(".shp.iso.xml") or p.name.lower().endswith(".shp.xml"))
    ]

    orphaned = []
    for sidecar in sidecars:
        primary = primary_for_sidecar(sidecar)
        if primary is not None and not primary.exists():
            orphaned.append(sidecar)

    audit.metrics["shapefiles"]["orphaned_sidecar_count"] = len(orphaned)

    if orphaned:
        audit.add("WARN", "shapefiles", "orphaned_sidecars", f"Found {len(orphaned)} sidecar-like file(s) without matching .shp primary. Some .dbf files may be standalone tables; review before deleting.", evidence=[safe_rel(p, geodata_root) for p in orphaned[:50]])
    else:
        audit.add("PASS", "shapefiles", "orphaned_sidecars", "No orphaned shapefile sidecars detected in the shapefile search root.", search_root)

    return shapefiles


def list_layers_with_optional_tools(path: Path) -> Tuple[Optional[List[str]], str]:
    fiona, fiona_error = import_optional("fiona")
    if fiona is not None:
        try:
            return list(fiona.listlayers(path)), "fiona"
        except Exception as exc:
            fiona_error = f"{type(exc).__name__}: {exc}"

    pyogrio, pyogrio_error = import_optional("pyogrio")
    if pyogrio is not None:
        try:
            layers = pyogrio.list_layers(path)
            names = []
            for item in layers:
                if isinstance(item, (list, tuple)) and item:
                    names.append(str(item[0]))
                else:
                    names.append(str(item))
            return names, "pyogrio"
        except Exception as exc:
            pyogrio_error = f"{type(exc).__name__}: {exc}"

    ogrinfo = shutil.which("ogrinfo")
    if ogrinfo:
        try:
            proc = subprocess.run([ogrinfo, "-ro", "-so", str(path)], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            if proc.returncode != 0:
                return None, f"ogrinfo error: {proc.stderr.strip() or proc.stdout.strip()}"
            layers = []
            for line in proc.stdout.splitlines():
                match = re.match(r"^\s*\d+:\s+([^(\n]+)", line)
                if match:
                    layers.append(match.group(1).strip())
            return layers, "ogrinfo"
        except Exception as exc:
            return None, f"ogrinfo {type(exc).__name__}: {exc}"

    return None, "; ".join(x for x in [f"fiona unavailable or failed ({fiona_error})", f"pyogrio unavailable or failed ({pyogrio_error})", "ogrinfo not found"] if x)


def audit_tiger_vectors(audit: Audit, geodata_root: Path, geodb_dir: Optional[Path], no_vector_read: bool) -> None:
    search_root = geodb_dir if geodb_dir and geodb_dir.exists() else geodata_root

    gpkg_files = sorted(p for p in search_root.rglob("*.gpkg") if p.is_file())
    gdb_dirs = sorted(p for p in search_root.rglob("*.gdb") if p.is_dir())

    tiger_candidates = [
        p for p in [*gpkg_files, *gdb_dirs]
        if any(marker in p.name.lower() for marker in ["tiger", "tlg", "2025", "_72_", "72_pr", "pr"])
    ]
    primary_candidates = [p for p in tiger_candidates if any(marker in p.name.lower() for marker in ["2025", "72", "pr", "tlg"])] or tiger_candidates

    audit.metrics["tiger_vectors"] = {
        "search_root": str(search_root),
        "gpkg_count": len(gpkg_files),
        "gdb_count": len(gdb_dirs),
        "candidate_count": len(primary_candidates),
        "candidates": [safe_rel(p, geodata_root) for p in primary_candidates],
    }

    if not primary_candidates:
        audit.add("FAIL", "tiger", "container_presence", "No candidate TIGER/PR GPKG or GDB containers found.", search_root)
        return

    audit.add("PASS", "tiger", "container_presence", f"Found {len(primary_candidates)} candidate TIGER/PR vector container(s).", search_root, [safe_rel(p, geodata_root) for p in primary_candidates])

    empty_files = [p for p in gpkg_files if p.stat().st_size == 0]
    if empty_files:
        audit.add("FAIL", "tiger", "zero_byte_containers", f"Found {len(empty_files)} zero-byte GPKG file(s).", evidence=[safe_rel(p, geodata_root) for p in empty_files])
    else:
        audit.add("PASS", "tiger", "zero_byte_containers", "No zero-byte GPKG files found among vector containers.", search_root)

    if no_vector_read:
        audit.add("WARN", "tiger", "readability", "Vector read disabled by --no-vector-read; TIGER layer readability not verified.")
        return

    readability: Dict[str, Any] = {}
    road_layer_hits: Dict[str, List[str]] = {}
    read_failures: Dict[str, str] = {}

    for container in primary_candidates:
        layers, method = list_layers_with_optional_tools(container)
        key = safe_rel(container, geodata_root)
        if layers is None:
            read_failures[key] = method
            continue

        readability[key] = {"method": method, "layer_count": len(layers), "sample_layers": layers[:40]}
        road_hits = [layer for layer in layers if any(marker in layer.lower() for marker in ROAD_LAYER_MARKERS)]
        if road_hits:
            road_layer_hits[key] = road_hits[:40]

    audit.metrics["tiger_vectors"]["readability"] = readability
    audit.metrics["tiger_vectors"]["read_failures"] = read_failures
    audit.metrics["tiger_vectors"]["road_layer_hits"] = road_layer_hits

    if read_failures and not readability:
        audit.add("WARN", "tiger", "readability", "Could not read candidate TIGER vector containers with available local tools. This is a warning if GIS libraries are missing; it is a blocker if libraries are installed and paths are local.", evidence=read_failures)
        return

    if read_failures:
        audit.add("WARN", "tiger", "readability", f"{len(read_failures)} candidate vector container(s) could not be read, but at least one was readable.", evidence=read_failures)
    else:
        audit.add("PASS", "tiger", "readability", "All candidate TIGER/PR vector containers opened successfully.", evidence=readability)

    if road_layer_hits:
        audit.add("PASS", "tiger", "road_layer_presence", "Detected road/edge-like layer names in readable TIGER container(s).", evidence=road_layer_hits)
    else:
        audit.add("WARN", "tiger", "road_layer_presence", "No road/edge-like layers detected in readable vector containers. Signature 3 and Signature 7 should not run until road layers are confirmed.", evidence=readability)


def should_skip_text_scan_dir(path: Path) -> bool:
    return any(part in EXCLUDE_DIR_NAMES for part in path.parts)


def iter_text_files(repo_root: Path, max_file_mb: float) -> Iterable[Path]:
    max_bytes = int(max_file_mb * 1024 * 1024)
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if should_skip_text_scan_dir(path.relative_to(repo_root)):
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
        except OSError:
            continue
        yield path


def audit_pipeline_paths(audit: Audit, geodata_root: Path, repo_root_input: Optional[str], max_file_mb: float) -> None:
    if not repo_root_input:
        audit.add("WARN", "pipeline_paths", "repo_root_provided", "No --repo-root provided; pipeline path references were not scanned.")
        audit.metrics["pipeline_paths"] = {"scanned": False}
        return

    repo_root = Path(repo_root_input).expanduser().resolve()
    audit.metrics["pipeline_paths"] = {"repo_root": str(repo_root), "scanned": True}

    if not repo_root.exists() or not repo_root.is_dir():
        audit.add("FAIL", "pipeline_paths", "repo_root_exists", "Provided --repo-root does not exist or is not a directory.", repo_root)
        return

    stale_hits: List[Dict[str, str]] = []
    expected_hits: List[Dict[str, str]] = []
    scanned_count = 0

    for file_path in iter_text_files(repo_root, max_file_mb=max_file_mb):
        scanned_count += 1
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = safe_rel(file_path, repo_root)
        for marker in STALE_PATH_MARKERS:
            if marker in text:
                stale_hits.append({"file": rel, "marker": marker})
        for marker in EXPECTED_PATH_MARKERS:
            if marker in text:
                expected_hits.append({"file": rel, "marker": marker})

    audit.metrics["pipeline_paths"]["files_scanned"] = scanned_count
    audit.metrics["pipeline_paths"]["stale_hits"] = stale_hits
    audit.metrics["pipeline_paths"]["expected_hits"] = expected_hits

    if stale_hits:
        audit.add("FAIL", "pipeline_paths", "stale_path_references", "Found stale pre-reorganization path reference(s). Update these before running the ILAP DEM pilot.", evidence=stale_hits[:50])
    else:
        audit.add("PASS", "pipeline_paths", "stale_path_references", "No known stale pre-reorganization path markers found.", repo_root)

    if expected_hits:
        audit.add("PASS", "pipeline_paths", "expected_path_references", "Found PR_Geodata / 01_DEM_1m_LiDAR path reference(s) in repo text files.", evidence=expected_hits[:50])
    else:
        audit.add("WARN", "pipeline_paths", "expected_path_references", "No explicit PR_Geodata / 01_DEM_1m_LiDAR path references found. This may be okay if paths are only passed through CLI args.", repo_root)

    expected_dem = geodata_root / EXPECTED_CORE_DIRS["dem"]
    if expected_dem.exists():
        audit.add("PASS", "pipeline_paths", "expected_dem_folder_exists", "Expected DEM folder exists at PR_Geodata/01_DEM_1m_LiDAR.", expected_dem)
    else:
        audit.add("FAIL", "pipeline_paths", "expected_dem_folder_exists", "Expected DEM folder is missing: PR_Geodata/01_DEM_1m_LiDAR.", expected_dem)


def write_json_report(audit: Audit, output_dir: Path, status: str, args: argparse.Namespace) -> Path:
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "severity_counts": audit.severity_counts(),
        "args": vars(args),
        "metrics": audit.metrics,
        "findings": [asdict(f) for f in audit.findings],
    }
    path = output_dir / "pr_geodata_integrity_audit.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_csv_findings(audit: Audit, output_dir: Path) -> Path:
    path = output_dir / "pr_geodata_integrity_findings.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "category", "check", "message", "path", "evidence"])
        writer.writeheader()
        for finding in audit.findings:
            writer.writerow(asdict(finding))
    return path


def markdown_escape(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def remediation_for_status(status: str) -> List[str]:
    if status == "GO":
        return ["Proceed to the one-tile DEM pilot.", "Run score sanity checks before expanding to Arecibo/Utuado or islandwide batches."]
    if status == "CONDITIONAL_GO":
        return ["Review WARN findings before the pilot.", "Install optional GIS tooling if CRS or vector readability checks were skipped: rasterio plus fiona or pyogrio.", "Proceed only with signatures whose required layers were verified."]
    return ["Do not run ILAP DEM scoring yet.", "Fix all FAIL findings first.", "Re-run this audit until status is GO or an explicitly accepted CONDITIONAL_GO."]


def write_markdown_report(audit: Audit, output_dir: Path, status: str) -> Path:
    path = output_dir / "PR_GEODATA_INTEGRITY_GO_NO_GO.md"
    counts = audit.severity_counts()
    metrics = audit.metrics

    lines: List[str] = []
    lines.append("# PR Geodata Integrity Audit — GO / NO-GO Report")
    lines.append("")
    lines.append(f"Generated UTC: `{dt.datetime.now(dt.timezone.utc).isoformat()}`")
    lines.append("")
    lines.append(f"## Final status: `{status}`")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for key in ["FAIL", "WARN", "PASS", "INFO"]:
        lines.append(f"| {key} | {counts.get(key, 0)} |")

    lines.append("")
    lines.append("## Core metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Geodata root | `{markdown_escape(metrics.get('geodata_root', ''))}` |")

    dem = metrics.get("dem", {})
    lines.append(f"| DEM tile count | `{dem.get('tile_count', 'n/a')}` / expected `{dem.get('expected_tile_count', 'n/a')}` |")
    lines.append(f"| DEM total size | `{dem.get('total_size_human', 'n/a')}` |")
    lines.append(f"| DEM CRS counts | `{markdown_escape(dem.get('crs_counts', 'not verified'))}` |")
    lines.append(f"| DEM resolution counts | `{markdown_escape(dem.get('resolution_counts', 'not verified'))}` |")

    shp = metrics.get("shapefiles", {})
    lines.append(f"| Shapefile count | `{shp.get('count', 'n/a')}` |")
    lines.append(f"| Missing required shapefile sidecars | `{shp.get('missing_required_sidecar_count', 'n/a')}` |")
    lines.append(f"| Orphaned sidecars | `{shp.get('orphaned_sidecar_count', 'n/a')}` |")

    tiger = metrics.get("tiger_vectors", {})
    lines.append(f"| TIGER candidate containers | `{tiger.get('candidate_count', 'n/a')}` |")
    lines.append(f"| TIGER road layer hits | `{markdown_escape(tiger.get('road_layer_hits', 'not verified'))}` |")

    pipeline = metrics.get("pipeline_paths", {})
    lines.append(f"| Pipeline files scanned | `{pipeline.get('files_scanned', 'not scanned')}` |")
    lines.append(f"| Stale path hits | `{len(pipeline.get('stale_hits', [])) if isinstance(pipeline.get('stale_hits', []), list) else 'n/a'}` |")
    lines.append(f"| Expected path hits | `{len(pipeline.get('expected_hits', [])) if isinstance(pipeline.get('expected_hits', []), list) else 'n/a'}` |")

    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("| Severity | Category | Check | Message | Path | Evidence |")
    lines.append("|---|---|---|---|---|---|")

    severity_order = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3}
    for finding in sorted(audit.findings, key=lambda f: (severity_order.get(f.severity, 99), f.category, f.check)):
        evidence = finding.evidence
        if len(evidence) > 500:
            evidence = evidence[:500] + "..."
        lines.append(
            "| {severity} | {category} | {check} | {message} | `{path}` | `{evidence}` |".format(
                severity=markdown_escape(finding.severity),
                category=markdown_escape(finding.category),
                check=markdown_escape(finding.check),
                message=markdown_escape(finding.message),
                path=markdown_escape(finding.path),
                evidence=markdown_escape(evidence),
            )
        )

    lines.append("")
    lines.append("## Required action")
    lines.append("")
    for item in remediation_for_status(status):
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## ILAP pilot rule")
    lines.append("")
    lines.append("No DEM anomaly count, ILAP_SCORE, candidate coordinate, or field-validation class should be trusted until this audit passes and the downstream score-sum sanity check passes.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def print_console_summary(audit: Audit, status: str, output_paths: Sequence[Path]) -> None:
    counts = audit.severity_counts()
    print("")
    print("PR Geodata Integrity Audit")
    print("=" * 28)
    print(f"Status: {status}")
    print(f"Findings: FAIL={counts.get('FAIL', 0)} WARN={counts.get('WARN', 0)} PASS={counts.get('PASS', 0)} INFO={counts.get('INFO', 0)}")
    print("")
    print("Reports:")
    for path in output_paths:
        print(f"  - {path}")
    print("")

    critical = [f for f in audit.findings if f.severity in {"FAIL", "WARN"}]
    if critical:
        print("Blocking / review findings:")
        for finding in critical[:20]:
            print(f"  [{finding.severity}] {finding.category}.{finding.check}: {finding.message}")
        if len(critical) > 20:
            print(f"  ... {len(critical) - 20} more in the markdown/CSV reports")
    else:
        print("No FAIL/WARN findings.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local integrity audit for PR_Geodata before ILAP DEM anomaly processing.")
    parser.add_argument("--geodata-root", default=None, help="Path to PR_Geodata. If omitted, the script probes current directory and common local paths.")
    parser.add_argument("--repo-root", default=None, help="Optional repository root to scan for stale pipeline path references.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help=f"Directory where reports will be written. Default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--expected-dem-count", type=int, default=DEFAULT_EXPECTED_DEM_COUNT, help=f"Expected number of main DEM GeoTIFF tiles. Default: {DEFAULT_EXPECTED_DEM_COUNT}")
    parser.add_argument("--sample-dem-limit", type=int, default=25, help="Number of DEM tiles to sample for CRS/resolution if --all-dem-crs is not set.")
    parser.add_argument("--all-dem-crs", action="store_true", help="Read every DEM tile for CRS/resolution inventory instead of sampling.")
    parser.add_argument("--no-raster-read", action="store_true", help="Do not open DEM rasters; only count/check file sizes.")
    parser.add_argument("--no-vector-read", action="store_true", help="Do not open GPKG/GDB vectors; only check container presence and sizes.")
    parser.add_argument("--strict", action="store_true", help="Treat WARN findings as NO_GO in the final status.")
    parser.add_argument("--max-text-file-mb", type=float, default=2.0, help="Maximum text file size to scan for pipeline path markers.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    geodata_root = discover_geodata_root(args.geodata_root)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    audit = Audit()

    resolved = audit_root_structure(audit, geodata_root)
    audit_dem(audit, geodata_root, resolved.get("dem"), args.expected_dem_count, args.sample_dem_limit, args.all_dem_crs, args.no_raster_read)
    audit_shapefiles(audit, geodata_root, resolved.get("shapefiles"))
    audit_tiger_vectors(audit, geodata_root, resolved.get("geodatabases"), args.no_vector_read)
    audit_pipeline_paths(audit, geodata_root, args.repo_root, args.max_text_file_mb)

    status = audit.gate_status(strict=args.strict)

    json_path = write_json_report(audit, output_dir, status, args)
    csv_path = write_csv_findings(audit, output_dir)
    md_path = write_markdown_report(audit, output_dir, status)

    print_console_summary(audit, status, [md_path, json_path, csv_path])
    return 0 if status in {"GO", "CONDITIONAL_GO"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
