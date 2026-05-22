"""
FR24 SIDECAR RECONCILIATION

Read-only Google Photos Takeout sidecar reconciliation for timestamp-renamed
FR24 screenshots. This module does not OCR images and does not mutate source
files. It links screenshots to supplemental-metadata JSON using image filename
timestamps and Google Takeout photoTakenTime/creationTime timestamps.

Outputs:
  - fr24_sidecar_reconciliation_candidates.csv
  - fr24_sidecar_reconciliation_summary.json
  - fr24_sidecar_reconciliation_resolved.csv
  - fr24_manifest_with_sidecars.csv
  - fr24_sidecar_review_queue.csv
  - fr24_sidecar_reconciliation_resolved_summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

IMAGE_EXTS = {".png", ".heic", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
DEFAULT_TZ = "America/Puerto_Rico"

DATE_NAME_RE = re.compile(
    r"(?P<y>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})[ _-]+(?P<h>\d{2})-(?P<mi>\d{2})-(?P<s>\d{2})",
    re.I,
)


def _tz(name: str):
    if ZoneInfo is None:
        return timezone.utc
    return ZoneInfo(name)


def image_dt_from_name(path: Path, tz_name: str = DEFAULT_TZ) -> Optional[datetime]:
    m = DATE_NAME_RE.search(path.stem)
    if not m:
        return None
    g = {k: int(v) for k, v in m.groupdict().items()}
    return datetime(g["y"], g["m"], g["d"], g["h"], g["mi"], g["s"], tzinfo=_tz(tz_name))


def parse_google_time(obj: object, tz_name: str = DEFAULT_TZ) -> Optional[datetime]:
    if not isinstance(obj, dict):
        return None
    ts = obj.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(_tz(tz_name))
    except Exception:
        return None


def load_sidecar(path: Path, tz_name: str = DEFAULT_TZ) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"path": path, "error": repr(exc)}
    return {
        "path": path,
        "title": data.get("title"),
        "description": data.get("description"),
        "photo_dt": parse_google_time(data.get("photoTakenTime"), tz_name),
        "creation_dt": parse_google_time(data.get("creationTime"), tz_name),
        "geoData": data.get("geoData"),
        "geoDataExif": data.get("geoDataExif"),
        "error": "",
    }


def iter_images(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def iter_sidecars(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def build_candidate_rows(root: Path, max_delta_seconds: int = 300, tz_name: str = DEFAULT_TZ) -> Tuple[List[dict], dict]:
    images = [
        {"path": p, "name": p.name, "dt_name": image_dt_from_name(p, tz_name), "suffix": p.suffix.lower()}
        for p in iter_images(root)
    ]
    sidecars = [load_sidecar(p, tz_name) for p in iter_sidecars(root)]

    sidecar_times: List[Tuple[datetime, str, dict]] = []
    for sidecar in sidecars:
        for kind in ("photo_dt", "creation_dt"):
            dt = sidecar.get(kind)
            if dt:
                sidecar_times.append((dt, kind, sidecar))

    rows: List[dict] = []
    matched = 0
    for image in images:
        img_dt = image["dt_name"]
        best: Optional[dict] = None
        if img_dt:
            for side_dt, kind, sidecar in sidecar_times:
                delta = abs((img_dt - side_dt).total_seconds())
                if best is None or delta < best["delta_seconds"]:
                    best = {
                        "delta_seconds": delta,
                        "sidecar_time_kind": kind,
                        "sidecar_path": sidecar["path"],
                        "sidecar_title": sidecar.get("title"),
                        "sidecar_time_pr": side_dt.isoformat(),
                    }
        if best and best["delta_seconds"] <= max_delta_seconds:
            matched += 1
            status = "candidate_match"
        else:
            status = "unmatched"
        rows.append(
            {
                "image_path": str(image["path"]),
                "image_name": image["name"],
                "image_dt_from_name_pr": img_dt.isoformat() if img_dt else "",
                "match_status": status,
                "delta_seconds": "" if best is None else round(best["delta_seconds"], 3),
                "sidecar_time_kind": "" if best is None else best["sidecar_time_kind"],
                "sidecar_path": "" if best is None else str(best["sidecar_path"]),
                "sidecar_title": "" if best is None else best.get("sidecar_title") or "",
                "sidecar_time_pr": "" if best is None else best["sidecar_time_pr"],
            }
        )
    summary = {
        "images": len(images),
        "sidecars": len(sidecars),
        "sidecar_times": len(sidecar_times),
        "candidate_matches_5min": matched,
        "unmatched": len(images) - matched,
    }
    return rows, summary


def _safe_delta(row: dict) -> float:
    try:
        return float(row.get("delta_seconds") or 999999999)
    except Exception:
        return 999999999


def match_band(delta: float) -> str:
    if delta <= 2:
        return "strong"
    if delta <= 60:
        return "reviewable"
    if delta <= 300:
        return "weak"
    return "unmatched"


def _image_preference(row: dict) -> tuple:
    name = row.get("image_name", "")
    has_duplicate_suffix = "_1." in name
    return (_safe_delta(row), 1 if has_duplicate_suffix else 0, len(name), name)


def resolve_one_to_one(rows: List[dict]) -> Tuple[List[dict], dict]:
    candidate_rows = [
        r
        for r in rows
        if r.get("match_status") == "candidate_match" and r.get("sidecar_path") and _safe_delta(r) <= 300
    ]
    by_sidecar: Dict[str, List[dict]] = defaultdict(list)
    for row in candidate_rows:
        by_sidecar[row["sidecar_path"]].append(row)

    chosen_by_image: Dict[str, dict] = {}
    for _sidecar_path, hits in by_sidecar.items():
        hits_sorted = sorted(hits, key=_image_preference)
        winner = dict(hits_sorted[0])
        winner["resolved_status"] = "matched_primary"
        winner["match_band"] = match_band(_safe_delta(winner))
        winner["sidecar_conflict_count"] = str(len(hits_sorted) - 1)
        chosen_by_image[winner["image_path"]] = winner

    resolved_rows: List[dict] = []
    for row in rows:
        image_path = row["image_path"]
        if image_path in chosen_by_image:
            out = dict(chosen_by_image[image_path])
        elif row.get("match_status") == "candidate_match" and row.get("sidecar_path"):
            out = dict(row)
            out["resolved_status"] = "sidecar_duplicate_conflict"
            out["match_band"] = match_band(_safe_delta(out))
            out["sidecar_conflict_count"] = ""
        else:
            out = dict(row)
            out["resolved_status"] = "unmatched_metadata_gap"
            out["match_band"] = "unmatched"
            out["sidecar_conflict_count"] = ""

        out["ocr_status"] = "eligible"
        if out["resolved_status"] == "unmatched_metadata_gap":
            out["review_status"] = "metadata_gap"
        elif out["match_band"] == "weak":
            out["review_status"] = "weak_sidecar_match_review"
        elif out["resolved_status"] == "sidecar_duplicate_conflict":
            out["review_status"] = "sidecar_conflict_review"
        else:
            out["review_status"] = "sidecar_linked"
        resolved_rows.append(out)

    counts = Counter(r["resolved_status"] for r in resolved_rows)
    bands = Counter(r["match_band"] for r in resolved_rows)
    review_counts = Counter(r["review_status"] for r in resolved_rows)
    summary = {
        "total_images": len(resolved_rows),
        "resolved_status_counts": dict(counts),
        "match_band_counts": dict(bands),
        "review_status_counts": dict(review_counts),
        "primary_sidecar_matches": counts.get("matched_primary", 0),
        "metadata_gaps": counts.get("unmatched_metadata_gap", 0),
        "sidecar_duplicate_conflicts": counts.get("sidecar_duplicate_conflict", 0),
    }
    return resolved_rows, summary


def _write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run(root: Path, output_dir: Path, max_delta_seconds: int = 300, tz_name: str = DEFAULT_TZ) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, summary = build_candidate_rows(root, max_delta_seconds, tz_name)
    candidate_csv = output_dir / "fr24_sidecar_reconciliation_candidates.csv"
    _write_csv(candidate_csv, candidates)
    summary["output_csv"] = str(candidate_csv)
    (output_dir / "fr24_sidecar_reconciliation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    resolved, resolved_summary = resolve_one_to_one(candidates)
    resolved_csv = output_dir / "fr24_sidecar_reconciliation_resolved.csv"
    manifest_csv = output_dir / "fr24_manifest_with_sidecars.csv"
    review_csv = output_dir / "fr24_sidecar_review_queue.csv"
    _write_csv(resolved_csv, resolved)
    _write_csv(manifest_csv, resolved)
    _write_csv(review_csv, [r for r in resolved if r["review_status"] != "sidecar_linked"])
    resolved_summary.update(
        {
            "output_csv": str(resolved_csv),
            "manifest_with_sidecars": str(manifest_csv),
            "review_queue": str(review_csv),
        }
    )
    (output_dir / "fr24_sidecar_reconciliation_resolved_summary.json").write_text(
        json.dumps(resolved_summary, indent=2), encoding="utf-8"
    )
    return resolved_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile timestamp-renamed FR24 screenshots with Google Takeout sidecars")
    parser.add_argument("--root", required=True, help="Screenshot corpus root")
    parser.add_argument("--output-dir", default="data/_manifests/fr24_audit", help="Output manifest directory")
    parser.add_argument("--max-delta-seconds", type=int, default=300)
    parser.add_argument("--timezone", default=DEFAULT_TZ)
    args = parser.parse_args()
    summary = run(Path(args.root), Path(args.output_dir), args.max_delta_seconds, args.timezone)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
