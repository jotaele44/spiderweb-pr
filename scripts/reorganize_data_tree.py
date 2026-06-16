#!/usr/bin/env python3
"""Non-breaking consolidation of the repo data/ tree and the PR_Geodata folder.

Actions (all moves logged, nothing deleted except empty dirs):

repo data/:
  1. Rename ``data/_staging_geo`` → ``data/sources`` (canonical local inputs).
  2. Copy upload-origin source datasets into ``data/sources`` (self-contained).
  3. Write ``data/sources/sources_manifest.json`` with lineage + sha256.
  4. Quarantine superseded working files (``*.bak``, probe dirs) into
     ``data/_quarantine/<date>_reorg/``.
  5. Write ``data/_manifests/data_tree_index.json`` (directory purpose index).

PR_Geodata:
  6. Quarantine duplicate exports in 06_Vector_GeoJSON / 08_Vector_GeoPackage
     into ``_quarantine_<date>_reorg/`` (size+stem match; the plain-named copy
     is kept; when only prefixed twins exist the domain-prefixed copy is kept).
  7. Remove empty ``_probe`` dir.
  8. Write ``00_CATALOG_files_<date>.csv`` (fresh stat-level walk) and
     ``_REORG_LOG_<date>.json``.

Explicitly NOT touched (non-breaking guarantees):
  - Code-referenced paths: data/tiger/, data/faa_registry/, boundary geojsons,
    data/gis_layers/, data/rlsm/, todays_batch*.csv (live
    working queue), data/census/, data/sites/, data/intake/.
  - PR_Geodata numbered core dirs expected by tools/pr_geodata_integrity_audit
    (01_DEM_1m_LiDAR, 03_Geodatabases, 05_Vector_Shapefiles), karst_geojson/
    (referenced by ILAP_Pipeline scripts), root catalogs and fetch scripts.

Duplicate rule: candidate ``<prefix>__<stem>`` is quarantined only when a kept
counterpart with the same stem exists in the same dir AND byte size matches
exactly. Size-only matching is used because cloud-evicted files cannot be
hashed without forcing downloads; quarantine is fully reversible.

Usage:
    python3 scripts/reorganize_data_tree.py --geodata-root <PR_Geodata> [--execute]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

PREFIX_RE = re.compile(r"^([a-z0-9_]+?)__(.+)$", re.IGNORECASE)

# Upload-origin inputs the populate script parses — copied into data/sources.
SOURCE_FILES = [
    "pr_spiderweb_nodes_v5.csv",
    "pr_spiderweb_edges_v5.csv",
    "PR_Hydro_Layer_100pct_Normalized_Points.csv",
    "PR_WaterWorks_MasterDataset_v1.csv",
    "Spiderweb_Verified_Batch1_to_4_with_Resolved.csv",
    "Spiderweb_Consolidated_Dataset_v1_4.sqlite",
    "Spiderweb_Consolidated_Dataset_v4.sqlite",
    "PR_Landing_Zones_Master.gpkg",
    "Military & Aviation.gpkg",
    "PR_Industrial_AllTypes_Master.gpkg",
    "NID_v1_-639595725017535442.gpkg",
    "PRI.gpkg",
    "Spiderweb_Hydro_Master_v3.gpkg",
]

DIR_PURPOSES = {
    "sources": "Canonical local copies of external source datasets parsed by "
               "scripts/populate_dataset_layers.py (lineage in sources_manifest.json).",
    "gis_layers": "Normalized EPSG:4326 GeoJSON dataset layers + per-feature _meta "
                  "(built by scripts/populate_dataset_layers.py).",
    "_manifests": "Machine-readable manifests/indexes for data/ artifacts.",
    "_quarantine": "Superseded/duplicate files moved here instead of deleted (dated subdirs).",
    "tiger": "TIGER/Line source data (code-referenced; do not move).",
    "faa_registry": "FAA aircraft registry source data (code-referenced; do not move).",
    "rlsm": "RLSM screenshot-analysis runtime DB (schema.sql + HANDOFF committed).",
    "census": "Census geography collection lists.",
    "intake": "PR intake derivatives lane (committed README/CSV).",
    "manual_logs": "Manually captured flight/ops logs.",
    "sites": "Site review packets (SITE_* dirs).",
    "_probe2": "QUARANTINED (probe junk).",
}

LOG: List[Dict] = []


def log(action: str, src: Path, dst: Optional[Path], reason: str, **extra) -> None:
    LOG.append({"action": action, "src": str(src), "dst": str(dst) if dst else None,
                "reason": reason, **extra})


def sha256(p: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def move(src: Path, dst: Path, reason: str, execute: bool) -> None:
    log("move", src, dst, reason)
    if execute:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite: shutil.move clobbers an existing file (or moves INTO an
        # existing directory), which would make quarantine non-reversible if a
        # prior run already placed a same-name file. Uniquify the destination.
        if dst.exists():
            i = 1
            while True:
                cand = dst.with_name(f"{dst.stem}__dup{i}{dst.suffix}")
                if not cand.exists():
                    dst = cand
                    break
                i += 1
            log("move", src, dst, reason + " (dst existed; uniquified)")
        shutil.move(str(src), str(dst))


# ── repo data/ ────────────────────────────────────────────────────────────────


def reorg_repo(uploads: Optional[Path], execute: bool) -> None:
    data = REPO_ROOT / "data"
    q = data / "_quarantine" / f"{TODAY}_reorg"

    # 1. staging → sources
    staging, sources = data / "_staging_geo", data / "sources"
    if staging.exists() and not sources.exists():
        move(staging, sources, "rename staging dir to canonical data/sources", execute)
    elif not execute and staging.exists():
        log("move", staging, sources, "rename staging dir to canonical data/sources")

    src_dir = sources if (sources.exists() or execute) else staging

    # 2. copy upload-origin inputs in
    entries = []
    for name in SOURCE_FILES:
        dst = src_dir / name
        if dst.exists():
            entries.append((dst, "already_present"))
            continue
        found = None
        if uploads:
            cand = uploads / name
            if cand.exists():
                found = cand
        if found is None:
            log("gap", src_dir / name, None, "source file not found in uploads; not copied")
            continue
        log("copy", found, dst, "consolidate upload-origin source into data/sources")
        if execute:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(found), str(dst))
        entries.append((dst, "copied_from_uploads"))

    # 3. sources manifest with lineage
    if execute:
        man = []
        for p in sorted(src_dir.iterdir()):
            if p.name == "sources_manifest.json" or p.is_dir():
                continue
            man.append({
                "file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p),
                "origin": ("PR_Geodata staging copy" if p.suffix == ".geojson"
                           or p.name == "PR_Karst_Subsurface_v2.gpkg"
                           else "session uploads"),
                "role": "parsed_input",
            })
        (src_dir / "sources_manifest.json").write_text(json.dumps({
            "manifest_id": "data_sources_manifest", "produced_at": RUN_TS,
            "producer_module": "scripts.reorganize_data_tree",
            "note": "Canonical local inputs for scripts/populate_dataset_layers.py; "
                    "originals live in ~/Documents/Data/PR_Geodata and session uploads.",
            "files": man,
        }, indent=2), encoding="utf-8")
        log("write", src_dir / "sources_manifest.json", None, "lineage manifest")

    # 4. quarantine superseded working files
    for rel in ["todays_batch.PRE-REBUILD-2026-06-10.csv.bak", "_probe2"]:
        p = data / rel
        if p.exists():
            move(p, q / rel, "superseded backup/probe artifact", execute)

    # 5. tree index
    if execute:
        idx = []
        for p in sorted(data.iterdir()):
            if p.name.startswith(".") or p.name == "todays_batch.PRE-REBUILD-2026-06-10.csv.bak":
                continue
            n_files = sum(1 for _ in p.rglob("*") if _.is_file()) if p.is_dir() else 1
            idx.append({"name": p.name, "type": "dir" if p.is_dir() else "file",
                        "files": n_files,
                        "purpose": DIR_PURPOSES.get(p.name,
                                   "working file" if p.is_file() else "working dir"),
                        "code_referenced": p.name in
                        {"tiger", "faa_registry", "gis_layers", "_manifests", "sources",
                         "barrios.geojson", "municipios.geojson", "places.geojson",
                         "tracts.geojson", "sites"}})
        (data / "_manifests" / "data_tree_index.json").write_text(json.dumps({
            "index_id": "data_tree_index", "produced_at": RUN_TS,
            "producer_module": "scripts.reorganize_data_tree", "entries": idx,
        }, indent=2), encoding="utf-8")
        log("write", data / "_manifests" / "data_tree_index.json", None, "directory index")


# ── PR_Geodata ───────────────────────────────────────────────────────────────


def dedupe_dir(d: Path, qroot: Path, execute: bool) -> None:
    files = {p.name: p.stat().st_size for p in d.iterdir() if p.is_file()}
    moved = set()
    # pass 1: prefixed copy whose plain counterpart exists with identical size
    for name, size in sorted(files.items()):
        m = PREFIX_RE.match(name)
        if not m:
            continue
        stem = m.group(2)
        if stem in files and files[stem] == size:
            move(d / name, qroot / d.name / name,
                 f"duplicate of kept '{stem}' (size match {size} B, stem match)", execute)
            moved.add(name)
    # pass 2: twin prefixed copies with no matching plain — keep the
    # domain-prefixed (non geojson__) one, quarantine the geojson__ twin
    for name, size in sorted(files.items()):
        if name in moved or not name.startswith("geojson__"):
            continue
        stem = name[len("geojson__"):]
        twins = [n for n, s in files.items()
                 if n not in moved and n != name and s == size
                 and (PREFIX_RE.match(n) and PREFIX_RE.match(n).group(2) == stem)]
        if twins:
            move(d / name, qroot / d.name / name,
                 f"duplicate of kept '{twins[0]}' (size match {size} B, stem match)", execute)
            moved.add(name)


def reorg_geodata(root: Path, execute: bool) -> None:
    qroot = root / f"_quarantine_{TODAY}_reorg"
    for sub in ("06_Vector_GeoJSON", "08_Vector_GeoPackage"):
        d = root / sub
        if d.exists():
            dedupe_dir(d, qroot, execute)
    probe = root / "_probe"
    if probe.exists() and not any(probe.iterdir()):
        if execute:
            try:
                probe.rmdir()
                log("rmdir", probe, None, "empty probe dir")
            except OSError:
                try:
                    shutil.move(str(probe), str(qroot / "_probe"))
                    log("move", probe, qroot / "_probe",
                        "empty probe dir (rmdir blocked by mount; quarantined instead)")
                except OSError as exc:
                    log("gap", probe, None,
                        f"could not remove or move empty probe dir ({exc}); left in place")
        else:
            log("rmdir", probe, None, "empty probe dir")
    # fresh stat-level catalog
    if execute:
        cat = root / f"00_CATALOG_files_{TODAY}.csv"
        with open(cat, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["relpath", "bytes", "mtime_utc", "top_dir"])
            for p in sorted(root.rglob("*")):
                if p.is_file() and not p.name.startswith("."):
                    rel = p.relative_to(root)
                    st = p.stat()
                    w.writerow([str(rel), st.st_size,
                                datetime.fromtimestamp(st.st_mtime, timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                                rel.parts[0] if len(rel.parts) > 1 else "(root)"])
        log("write", cat, None, "fresh catalog (stat-level walk; supplements 00_CATALOG_files.csv)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geodata-root", type=Path, required=True)
    ap.add_argument("--uploads", type=Path, default=None)
    ap.add_argument("--execute", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()

    reorg_repo(args.uploads, args.execute)
    reorg_geodata(args.geodata_root, args.execute)

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"[{mode}] {len(LOG)} actions")
    for e in LOG:
        print(f"  {e['action']:6} {e['src']}" + (f" → {e['dst']}" if e["dst"] else "")
              + f"  ({e['reason']})")
    out = {"reorg_id": f"data_reorg_{TODAY}", "mode": mode, "produced_at": RUN_TS,
           "actions": LOG}
    if args.execute:
        (REPO_ROOT / "data" / "_manifests" / f"reorg_log_{TODAY}.json").write_text(
            json.dumps(out, indent=2), encoding="utf-8")
        (args.geodata_root / f"_REORG_LOG_{TODAY}.json").write_text(
            json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
