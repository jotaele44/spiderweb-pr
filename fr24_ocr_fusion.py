"""
FR24 OCR FUSION

Fuses whole-image OCR parser output with region OCR parser output. Conflicting
field values are preserved side-by-side and routed to review; the fusion layer
never confirms aircraft events or overwrites source evidence silently.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

FUSION_VERSION = "fr24_ocr_fusion_v0.1.0"
FUSION_FIELDS = [
    "callsign_or_label",
    "operator",
    "aircraft_type",
    "registration",
    "origin_code",
    "destination_code",
    "barometric_altitude_ft",
    "ground_speed_mph",
    "flight_status",
    "elapsed_departed",
    "elapsed_arrived",
    "playback_date",
    "playback_time",
    "playback_timezone",
]
REGION_PRIORITY = {
    "right_panel": 0,
    "bottom_timeline": 1,
    "full_image": 2,
    "map_area": 3,
    "top_bar": 4,
}


def read_csv(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def write_csv(path: Path, rows: List[dict], fieldnames: List[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else []
    if not fieldnames:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def region_sort_key(row: dict) -> tuple:
    try:
        confidence = float(row.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    return (REGION_PRIORITY.get(row.get("region_name", ""), 99), -confidence, row.get("region_name", ""))


def best_region_rows(region_rows: Iterable[dict]) -> Dict[str, dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in region_rows:
        grouped[row.get("image_path", "")].append(row)
    return {image_path: sorted(rows, key=region_sort_key)[0] for image_path, rows in grouped.items() if image_path}


def values_conflict(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a.strip().lower() != b.strip().lower()


def fuse_row(whole: dict, region: dict | None) -> dict:
    image_path = whole.get("image_path", "") or (region or {}).get("image_path", "")
    image_name = whole.get("image_name", "") or (region or {}).get("image_name", "")
    out = {
        "candidate_id": f"fused::{Path(image_path).name}",
        "image_path": image_path,
        "image_name": image_name,
        "whole_review_status": whole.get("review_status", ""),
        "region_review_status": (region or {}).get("review_status", ""),
        "region_name": (region or {}).get("region_name", ""),
        "whole_confidence": whole.get("confidence", ""),
        "region_confidence": (region or {}).get("confidence", ""),
        "field_conflicts": "",
        "conflict_count": 0,
        "fusion_status": "fused_candidate",
        "review_status": "fused_candidate",
        "fusion_version": FUSION_VERSION,
        "confirmation_status": "not_confirmed",
    }
    conflicts: List[str] = []
    for field in FUSION_FIELDS:
        wi_value = whole.get(field, "")
        region_value = (region or {}).get(field, "")
        out[f"{field}_wi"] = wi_value
        out[f"{field}_region"] = region_value
        if values_conflict(wi_value, region_value):
            conflicts.append(field)
    out["field_conflicts"] = ";".join(conflicts)
    out["conflict_count"] = len(conflicts)

    if conflicts:
        out["fusion_status"] = "fusion_conflict_review"
        out["review_status"] = "fusion_conflict_review"
    elif whole.get("review_status") == "manual_review_required" or (region or {}).get("review_status") in {"region_manual_review_required", "region_low_text_review", "region_ocr_failed"}:
        out["fusion_status"] = "manual_review_required"
        out["review_status"] = "manual_review_required"
    return out


def fuse(whole_image_csv: Path, region_csv: Path, output_csv: Path, review_csv: Path) -> dict:
    whole_rows = read_csv(whole_image_csv)
    region_rows = read_csv(region_csv)
    best_regions = best_region_rows(region_rows)

    fused: List[dict] = []
    seen_images = set()
    for whole in whole_rows:
        image_path = whole.get("image_path", "")
        fused.append(fuse_row(whole, best_regions.get(image_path)))
        seen_images.add(image_path)

    # Region-only candidates are retained, but review-gated.
    for image_path, region in best_regions.items():
        if image_path in seen_images:
            continue
        empty_whole = {"image_path": image_path, "image_name": region.get("image_name", ""), "review_status": "missing_whole_image_parse"}
        fused_row = fuse_row(empty_whole, region)
        fused_row["fusion_status"] = "region_only_review"
        fused_row["review_status"] = "region_only_review"
        fused.append(fused_row)

    fieldnames = list(fused[0].keys()) if fused else []
    write_csv(output_csv, fused, fieldnames)
    review_rows = [r for r in fused if r.get("review_status") != "fused_candidate"]
    write_csv(review_csv, review_rows, fieldnames)

    summary = {
        "whole_rows": len(whole_rows),
        "region_rows": len(region_rows),
        "fused_rows": len(fused),
        "review_rows": len(review_rows),
        "review_status": dict(Counter(r.get("review_status", "") for r in fused)),
        "output_csv": str(output_csv),
        "review_csv": str(review_csv),
        "policy": "candidate_only_no_auto_confirmation",
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Fuse whole-image and region OCR parsed candidates")
    parser.add_argument("--whole-image-csv", default="data/_manifests/fr24_audit/fr24_ocr_parsed_events_probe_50.csv")
    parser.add_argument("--region-csv", default="data/_manifests/fr24_audit/fr24_region_parsed_events.csv")
    parser.add_argument("--output-csv", default="data/_manifests/fr24_audit/fr24_fused_event_candidates.csv")
    parser.add_argument("--review-csv", default="data/_manifests/fr24_audit/fr24_fused_review_queue.csv")
    args = parser.parse_args()
    print(json.dumps(fuse(Path(args.whole_image_csv), Path(args.region_csv), Path(args.output_csv), Path(args.review_csv)), indent=2))


if __name__ == "__main__":
    main()
