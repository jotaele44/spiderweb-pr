"""
FR24 REVIEW QUEUE BUILDER

Builds a priority review queue from fused OCR candidate rows. This utility only
prioritizes manual review; it does not confirm events.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import List


def read_csv(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def priority_score(row: dict) -> int:
    score = 0
    status = row.get("review_status", "")
    if status == "fusion_conflict_review":
        score += 50
    elif status == "region_only_review":
        score += 35
    elif status == "manual_review_required":
        score += 25
    try:
        score += min(20, int(row.get("conflict_count") or 0) * 5)
    except Exception:
        pass
    if row.get("registration_wi") or row.get("registration_region"):
        score += 10
    if row.get("aircraft_type_wi") or row.get("aircraft_type_region"):
        score += 8
    if row.get("barometric_altitude_ft_wi") or row.get("barometric_altitude_ft_region"):
        score += 4
    if row.get("ground_speed_mph_wi") or row.get("ground_speed_mph_region"):
        score += 4
    return score


def required_next_check(row: dict) -> str:
    if row.get("review_status") == "fusion_conflict_review":
        return "compare_whole_image_vs_region_ocr"
    if row.get("review_status") == "region_only_review":
        return "verify_missing_whole_image_parse"
    if row.get("review_status") == "manual_review_required":
        return "manual_ocr_field_review"
    return "spot_check_candidate"


def build_queue(fused_csv: Path, output_csv: Path) -> dict:
    rows = read_csv(fused_csv)
    queue = []
    for row in rows:
        if row.get("review_status") == "fused_candidate":
            continue
        out = dict(row)
        out["priority_score"] = priority_score(row)
        out["required_next_check"] = required_next_check(row)
        out["queue_status"] = "open"
        out["confirmation_status"] = "not_confirmed"
        queue.append(out)
    queue.sort(key=lambda r: (-int(r.get("priority_score") or 0), r.get("image_name", "")))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if queue:
        with output_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(queue[0].keys()))
            writer.writeheader()
            writer.writerows(queue)
    else:
        output_csv.write_text("", encoding="utf-8")
    summary = {
        "input_csv": str(fused_csv),
        "queue_rows": len(queue),
        "review_status": dict(Counter(r.get("review_status", "") for r in queue)),
        "output_csv": str(output_csv),
        "policy": "candidate_only_no_auto_confirmation",
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FR24 fused OCR review queue")
    parser.add_argument("--fused-csv", default="data/_manifests/fr24_audit/fr24_fused_event_candidates.csv")
    parser.add_argument("--output-csv", default="data/_manifests/fr24_audit/fr24_fused_review_queue_ranked.csv")
    args = parser.parse_args()
    print(json.dumps(build_queue(Path(args.fused_csv), Path(args.output_csv)), indent=2))


if __name__ == "__main__":
    main()
