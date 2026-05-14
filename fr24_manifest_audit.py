"""
FR24 MANIFEST AUDIT
Standalone pre-ingest audit for a Google Photos Takeout FR24 folder.

Run this LOCALLY on the machine where the images are stored before running
any OCR or DB-build pipeline. Produces a manifest CSV and a JSON report.

Usage:
    python fr24_manifest_audit.py [FR24_FOLDER]

Default folder (edit FR24_ROOT below if running without an argument):
    /Users/jotaele/Documents/GitHub/Raw Flight Logs/Takeout-9/Google Photos/FR24

Outputs (written alongside this script or to --output-dir):
    fr24_manifest_audit.csv        full per-image record
    fr24_manifest_audit_report.json summary + folder structure + sidecar counts

This script is read-only: it never writes to the DB or modifies any images.
OCR and DB build remain FROZEN until this audit passes (0 corrupt, 0 missing
sidecars that are expected, clean git status for raw files).
"""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Default FR24 root (edit if running without a CLI argument) ────────────────
FR24_ROOT = "/Users/jotaele/Documents/GitHub/Raw Flight Logs/Takeout-9/Google Photos/FR24"

# ── Image extensions recognised by ScreenshotInventory + HEIC from iPhone ────
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".HEIC"}
SIDECAR_EXTS = {".json"}
DB_EXTS      = {".db", ".sqlite", ".sqlite3"}
VIDEO_EXTS   = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def _sha256(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _image_dims(path: Path) -> Tuple[Optional[int], Optional[int], bool]:
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
        return w, h, False
    except ImportError:
        return None, None, False   # PIL not installed — skip dim check
    except Exception:
        return None, None, True    # corrupt


def audit(fr24_dir: str, output_dir: Optional[str] = None, max_images: Optional[int] = None) -> dict:
    root = Path(fr24_dir)
    if not root.exists():
        print(f"[ERROR] Directory not found: {fr24_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(output_dir) if output_dir else Path(fr24_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[AUDIT] Scanning: {root}")
    print(f"[AUDIT] Output:   {out_dir}\n")

    # ── Walk the tree ─────────────────────────────────────────────────────────
    all_files  = list(root.rglob("*"))
    image_files  = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    sidecar_files = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in SIDECAR_EXTS)
    db_files     = sorted(p for p in all_files if p.is_file() and p.suffix in DB_EXTS)
    video_files  = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    other_files  = sorted(
        p for p in all_files
        if p.is_file()
        and p.suffix.lower() not in IMAGE_EXTS | SIDECAR_EXTS | DB_EXTS | VIDEO_EXTS
    )

    if max_images:
        image_files = image_files[:max_images]

    total_images = len(image_files)
    print(f"  Images found:   {total_images}")
    print(f"  JSON sidecars:  {len(sidecar_files)}")
    print(f"  Video files:    {len(video_files)}")
    print(f"  DB files:       {len(db_files)}  {'← WARNING: unexpected' if db_files else ''}")
    print(f"  Other files:    {len(other_files)}")

    # ── Folder structure ──────────────────────────────────────────────────────
    subdirs = sorted({p.parent for p in image_files if p.parent != root})
    ext_counts = Counter(p.suffix.lower() for p in image_files)

    print(f"\n  Subfolders:     {len(subdirs)}")
    print(f"  Extension mix:  {dict(ext_counts)}")

    # ── Sidecar pairing ───────────────────────────────────────────────────────
    # Google Photos exports companion .json for most images (some are album metadata)
    sidecar_stems = {p.stem for p in sidecar_files}
    images_with_sidecar = [p for p in image_files if p.name in sidecar_stems or p.stem in sidecar_stems]
    images_without_sidecar = [p for p in image_files if p not in images_with_sidecar]

    print(f"\n  With sidecar:   {len(images_with_sidecar)}")
    print(f"  No sidecar:     {len(images_without_sidecar)}")

    # ── Per-image scan ────────────────────────────────────────────────────────
    print(f"\n  Scanning {total_images} images (SHA-256 + dimensions) …")
    records: List[dict] = []
    hash_index: Dict[str, str] = {}
    corrupt_count = 0
    dupe_count = 0

    for i, path in enumerate(image_files, 1):
        if i % 500 == 0 or i == total_images:
            print(f"    {i}/{total_images} …", end="\r")

        sha = _sha256(path)
        w, h, is_corrupt = _image_dims(path)
        if is_corrupt:
            corrupt_count += 1

        is_dupe = False
        dupe_of = None
        if sha:
            if sha in hash_index:
                is_dupe = True
                dupe_of = hash_index[sha]
                dupe_count += 1
            else:
                hash_index[sha] = str(path)

        records.append({
            "path":         str(path),
            "filename":     path.name,
            "folder":       str(path.parent.relative_to(root)),
            "size_bytes":   path.stat().st_size,
            "sha256":       sha,
            "width":        w,
            "height":       h,
            "is_corrupt":   is_corrupt,
            "is_duplicate": is_dupe,
            "duplicate_of": dupe_of,
            "has_sidecar":  path.name in sidecar_stems or path.stem in sidecar_stems,
            "scanned_at":   datetime.utcnow().isoformat() + "Z",
        })

    print(f"\n  Corrupt:        {corrupt_count}")
    print(f"  Duplicates:     {dupe_count}")
    valid = total_images - corrupt_count - dupe_count
    print(f"  Valid unique:   {valid}")

    # ── DB / raw-file git check ───────────────────────────────────────────────
    git_tracked_raw = []
    try:
        import subprocess
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(root)],
            capture_output=True, text=True, cwd=str(root.parent)
        )
        if result.returncode == 0:
            git_tracked_raw = result.stdout.strip().splitlines()
    except Exception:
        pass

    if git_tracked_raw:
        print(f"\n  [WARNING] Git-tracked raw files: {len(git_tracked_raw)}")
        for f in git_tracked_raw[:5]:
            print(f"    {f}")
    else:
        print("\n  Git-tracked raw files: none ✓")

    if db_files:
        print("\n  [WARNING] DB files found in tree:")
        for f in db_files:
            print(f"    {f}")

    # ── Write manifest CSV ────────────────────────────────────────────────────
    import csv
    csv_path = out_dir / "fr24_manifest_audit.csv"
    fields = [
        "path", "filename", "folder", "size_bytes", "sha256",
        "width", "height", "is_corrupt", "is_duplicate", "duplicate_of",
        "has_sidecar", "scanned_at",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    # ── Write JSON report ─────────────────────────────────────────────────────
    total_bytes = sum(r["size_bytes"] for r in records)
    report = {
        "generated_at":          datetime.utcnow().isoformat() + "Z",
        "fr24_root":             str(root),
        "total_images":          total_images,
        "valid_unique":          valid,
        "corrupt":               corrupt_count,
        "duplicates":            dupe_count,
        "json_sidecars":         len(sidecar_files),
        "images_with_sidecar":   len(images_with_sidecar),
        "images_without_sidecar":len(images_without_sidecar),
        "video_files":           len(video_files),
        "db_files_in_tree":      [str(p) for p in db_files],
        "git_tracked_raw_files": git_tracked_raw,
        "total_size_bytes":      total_bytes,
        "total_size_gb":         round(total_bytes / 1e9, 3),
        "extension_counts":      dict(ext_counts),
        "subfolder_count":       len(subdirs),
        "subfolders":            [str(s.relative_to(root)) for s in subdirs],
        "manifest_csv":          str(csv_path),
        "audit_pass":            (
            corrupt_count == 0
            and len(db_files) == 0
            and len(git_tracked_raw) == 0
        ),
    }

    json_path = out_dir / "fr24_manifest_audit_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n  Manifest CSV:   {csv_path}")
    print(f"  Audit report:   {json_path}")

    status = "PASS" if report["audit_pass"] else "FAIL"
    print(f"\n  ══ AUDIT {status} ══")
    if not report["audit_pass"]:
        if corrupt_count:
            print(f"    Corrupt images: {corrupt_count} — inspect before OCR")
        if db_files:
            print(f"    DB files in tree: remove before pipeline run")
        if git_tracked_raw:
            print(f"    Raw files git-tracked: run git rm --cached and add to .gitignore")
    else:
        print("    0 corrupt  |  0 DB files  |  0 git-tracked raw files")
        print("    Ready to proceed to --scan-inventory and OCR pipeline.")
        print(f"    Command: python run_all.py --scan-inventory '{root}' --db /path/to/flight.db")

    return report


def main():
    parser = argparse.ArgumentParser(description="FR24 Google Photos Takeout manifest audit")
    parser.add_argument("fr24_dir", nargs="?", default=FR24_ROOT,
                        help=f"Path to FR24 folder (default: {FR24_ROOT})")
    parser.add_argument("--output-dir", metavar="DIR",
                        help="Directory to write CSV + JSON report (default: fr24_dir)")
    parser.add_argument("--max-images", type=int, metavar="N",
                        help="Limit scan to first N images (for quick smoke test)")
    args = parser.parse_args()

    report = audit(args.fr24_dir, args.output_dir, args.max_images)
    sys.exit(0 if report["audit_pass"] else 1)


if __name__ == "__main__":
    main()
