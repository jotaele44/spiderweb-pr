"""
FR24 MANIFEST AUDIT
Standalone pre-ingest audit for a Google Photos Takeout FR24 folder.

Run this LOCALLY on the machine where the images are stored before running
any OCR or DB-build pipeline. Produces a manifest CSV and a JSON report.

Usage:
    python fr24_manifest_audit.py --root /path/to/FR24 --output-dir /tmp/fr24_audit
    python fr24_manifest_audit.py --root /path/to/FR24 --max-images 50

Default folder, if neither --root nor positional FR24_FOLDER is supplied:
    /Users/jotaele/Documents/GitHub/Raw Flight Logs/Takeout-9/Google Photos/FR24

Outputs:
    fr24_manifest_audit.csv         full per-image record
    fr24_manifest_audit_report.json summary + folder structure + sidecar counts

This script is read-only: it never writes to the DB or modifies any images.
OCR and DB build remain FROZEN until this audit passes.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Default FR24 root ─────────────────────────────────────────────────────────
FR24_ROOT = "/Users/jotaele/Documents/GitHub/Raw Flight Logs/Takeout-9/Google Photos/FR24"

# ── File classes ──────────────────────────────────────────────────────────────
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".heic"}
SIDECAR_EXTS = {".json"}
DB_EXTS = {".db", ".sqlite", ".sqlite3"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


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
        return None, None, False  # PIL not installed — skip dimension/corrupt check
    except Exception:
        return None, None, True


def _expected_sidecar_path(image_path: Path) -> Path:
    """Return the Google Photos Takeout sidecar path for an image.

    Example:
        IMG_0045.PNG -> IMG_0045.PNG.supplemental-metadata.json
    """
    return image_path.with_name(image_path.name + ".supplemental-metadata.json")


def _find_git_tracked_raw(root: Path) -> List[str]:
    """Return tracked raw files under root, if root is inside a Git checkout."""
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            return []

        repo_root = Path(probe.stdout.strip())
        listed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--", str(root)],
            capture_output=True,
            text=True,
        )
        if listed.returncode != 0 or not listed.stdout.strip():
            return []

        raw_exts = IMAGE_EXTS | SIDECAR_EXTS | VIDEO_EXTS | DB_EXTS
        return [
            line
            for line in listed.stdout.splitlines()
            if Path(line).suffix.lower() in raw_exts
        ]
    except Exception:
        return []


def audit(
    fr24_dir: str,
    output_dir: Optional[str] = None,
    max_images: Optional[int] = None,
    no_hash: bool = False,
    json_only: bool = False,
) -> dict:
    started = time.perf_counter()
    root = Path(fr24_dir).expanduser().resolve()
    if not root.exists():
        print(f"[ERROR] Directory not found: {fr24_dir}", file=sys.stderr)
        sys.exit(1)
    if not root.is_dir():
        print(f"[ERROR] Not a directory: {fr24_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(output_dir).expanduser().resolve() if output_dir else root
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_mode = "smoke" if max_images else "full"

    if not json_only:
        print(f"[AUDIT] Scanning: {root}")
        print(f"[AUDIT] Output:   {out_dir}")
        print(f"[AUDIT] Mode:     {audit_mode}\n")

    all_files = list(root.rglob("*"))
    image_files = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    sidecar_files = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in SIDECAR_EXTS)
    db_files = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in DB_EXTS)
    video_files = sorted(p for p in all_files if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    known_exts = IMAGE_EXTS | SIDECAR_EXTS | DB_EXTS | VIDEO_EXTS
    other_files = sorted(
        p for p in all_files if p.is_file() and p.suffix.lower() not in known_exts
    )

    full_image_count = len(image_files)
    if max_images:
        image_files = image_files[:max_images]

    total_images = len(image_files)
    ext_counts = Counter(p.suffix.lower() for p in image_files)
    subdirs = sorted({p.parent for p in image_files if p.parent != root})

    sidecar_paths = {p.resolve() for p in sidecar_files}
    images_with_sidecar: List[Path] = []
    images_without_sidecar: List[Path] = []
    sidecar_lookup: Dict[Path, bool] = {}
    for p in image_files:
        has_sidecar = _expected_sidecar_path(p).resolve() in sidecar_paths
        sidecar_lookup[p] = has_sidecar
        if has_sidecar:
            images_with_sidecar.append(p)
        else:
            images_without_sidecar.append(p)

    if not json_only:
        print(f"  Images found:   {total_images}")
        if max_images:
            print(f"  Full image set: {full_image_count}")
        print(f"  JSON sidecars:  {len(sidecar_files)}")
        print(f"  Video files:    {len(video_files)}")
        print(f"  DB files:       {len(db_files)}  {'← WARNING: unexpected' if db_files else ''}")
        print(f"  Other files:    {len(other_files)}")
        print(f"\n  Subfolders:     {len(subdirs)}")
        print(f"  Extension mix:  {dict(ext_counts)}")
        print(f"\n  With sidecar:   {len(images_with_sidecar)}")
        print(f"  No sidecar:     {len(images_without_sidecar)}")
        scan_label = "dimensions" if no_hash else "SHA-256 + dimensions"
        print(f"\n  Scanning {total_images} images ({scan_label}) …")

    records: List[dict] = []
    hash_index: Dict[str, str] = {}
    corrupt_count = 0
    dupe_count = 0

    for i, path in enumerate(image_files, 1):
        if not json_only and (i % 500 == 0 or i == total_images):
            print(f"    {i}/{total_images} …", end="\r")

        sha = None if no_hash else _sha256(path)
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
            "path": str(path),
            "filename": path.name,
            "folder": str(path.parent.relative_to(root)),
            "size_bytes": path.stat().st_size,
            "sha256": sha,
            "width": w,
            "height": h,
            "is_corrupt": is_corrupt,
            "is_duplicate": is_dupe,
            "duplicate_of": dupe_of,
            "has_sidecar": sidecar_lookup[path],
            "scanned_at": _utc_now(),
        })

    valid = total_images - corrupt_count - dupe_count
    git_tracked_raw = _find_git_tracked_raw(root)

    if not json_only:
        print(f"\n  Corrupt:        {corrupt_count}")
        print(f"  Duplicates:     {dupe_count}")
        print(f"  Valid unique:   {valid}")
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

    total_bytes = sum(r["size_bytes"] for r in records)
    elapsed_seconds = round(time.perf_counter() - started, 3)
    report = {
        "generated_at": _utc_now(),
        "audit_mode": audit_mode,
        "elapsed_seconds": elapsed_seconds,
        "fr24_root": str(root),
        "output_dir": str(out_dir),
        "full_image_count": full_image_count,
        "total_images": total_images,
        "valid_unique": valid,
        "corrupt": corrupt_count,
        "duplicates": dupe_count,
        "json_sidecars": len(sidecar_files),
        "images_with_sidecar": len(images_with_sidecar),
        "images_without_sidecar": len(images_without_sidecar),
        "sample_images_without_sidecar": [str(p) for p in images_without_sidecar[:10]],
        "video_files": len(video_files),
        "db_files_in_tree": [str(p) for p in db_files],
        "git_tracked_raw_files": git_tracked_raw,
        "total_size_bytes": total_bytes,
        "total_size_gb": round(total_bytes / 1e9, 3),
        "extension_counts": dict(sorted(ext_counts.items())),
        "subfolder_count": len(subdirs),
        "subfolders": [str(s.relative_to(root)) for s in subdirs],
        "manifest_csv": str(csv_path),
        "no_hash": no_hash,
        "audit_pass": (
            corrupt_count == 0
            and len(db_files) == 0
            and len(git_tracked_raw) == 0
        ),
    }

    json_path = out_dir / "fr24_manifest_audit_report.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if json_only:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"\n  Manifest CSV:   {csv_path}")
        print(f"  Audit report:   {json_path}")
        status = "PASS" if report["audit_pass"] else "FAIL"
        print(f"\n  ══ AUDIT {status} ══")
        if not report["audit_pass"]:
            if corrupt_count:
                print(f"    Corrupt images: {corrupt_count} — inspect before OCR")
            if db_files:
                print("    DB files in tree: remove before pipeline run")
            if git_tracked_raw:
                print("    Raw files git-tracked: run git rm --cached and add to .gitignore")
        else:
            print("    0 corrupt  |  0 DB files  |  0 git-tracked raw files")
            print("    Ready to proceed to --scan-inventory and OCR pipeline planning.")
            print(f"    Command: python run_all.py --scan-inventory '{root}' --db /path/to/flight.db")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="FR24 Google Photos Takeout manifest audit")
    parser.add_argument("fr24_dir", nargs="?", help="Path to FR24 folder")
    parser.add_argument("--root", metavar="DIR", help="Path to FR24 folder; overrides positional path")
    parser.add_argument("--output-dir", metavar="DIR", help="Directory to write CSV + JSON report")
    parser.add_argument("--max-images", type=int, metavar="N", help="Limit scan to first N images")
    parser.add_argument("--no-hash", action="store_true", help="Skip SHA-256 hashing for a faster count/dimension audit")
    parser.add_argument("--json-only", action="store_true", help="Print only the JSON report to stdout")
    args = parser.parse_args()

    root = args.root or args.fr24_dir or FR24_ROOT
    report = audit(root, args.output_dir, args.max_images, args.no_hash, args.json_only)
    sys.exit(0 if report["audit_pass"] else 1)


if __name__ == "__main__":
    main()
