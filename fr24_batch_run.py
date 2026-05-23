"""
FR24 BATCH RUNNER

Runs one planned FR24 OCR batch in either whole-image or region mode. The runner
is resumable, writes a ledger, writes per-batch status, and records failures in
an error queue instead of crashing the full batch.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageOps = None  # type: ignore

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    pass

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore

from fr24_region_ocr import REGION_FRACTIONS, crop_box

VALID_MODES = {"whole-image", "region"}


def read_csv(path: Path) -> List[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def append_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def completed_keys(ledger_path: Path, batch_id: str, mode: str) -> set[str]:
    rows = read_csv(ledger_path)
    return {
        r.get("run_key", "")
        for r in rows
        if r.get("batch_id") == batch_id and r.get("mode") == mode and r.get("status") == "complete"
    }


def ensure_ocr_ready() -> None:
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required")
    if pytesseract is None:
        raise RuntimeError("pytesseract is required")


def ocr_whole_image(image_path: Path) -> str:
    ensure_ocr_ready()
    with Image.open(image_path) as img:
        img.load()
        img = ImageOps.exif_transpose(img)
        img = img.convert("L")
        return pytesseract.image_to_string(img)


def ocr_region(image_path: Path, region_name: str) -> tuple[str, str]:
    ensure_ocr_ready()
    with Image.open(image_path) as img:
        img.load()
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        box = crop_box(width, height, REGION_FRACTIONS[region_name])
        crop = img.crop(box).convert("L")
        return pytesseract.image_to_string(crop), json.dumps(box)


def batch_rows(batch_plan: Path, batch_id: str, limit: int = 0) -> List[dict]:
    rows = [r for r in read_csv(batch_plan) if r.get("batch_id") == batch_id]
    if limit > 0:
        rows = rows[:limit]
    return rows


def run_batch(batch_plan: Path, batch_id: str, mode: str, output_dir: Path, limit: int = 0) -> dict:
    if mode not in VALID_MODES:
        raise SystemExit(f"--mode must be one of {sorted(VALID_MODES)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    batches_dir = output_dir / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "fr24_batch_run_ledger.csv"
    error_queue_path = output_dir / "fr24_batch_error_queue.csv"
    status_path = batches_dir / f"{batch_id}_{mode}_status.json"
    jsonl_path = batches_dir / f"{batch_id}_{mode}_ocr.jsonl"

    planned = batch_rows(batch_plan, batch_id, limit)
    done = completed_keys(ledger_path, batch_id, mode)
    ledger_rows: List[dict] = []
    error_rows: List[dict] = []
    json_records: List[dict] = []

    for row in planned:
        image_path = Path(row.get("image_path", ""))
        region_names = ["whole_image"] if mode == "whole-image" else list(REGION_FRACTIONS.keys())
        for region_name in region_names:
            run_key = f"{batch_id}::{mode}::{image_path}::{region_name}"
            if run_key in done:
                continue
            started_at = datetime.now(timezone.utc).isoformat()
            rec = {
                "run_key": run_key,
                "batch_id": batch_id,
                "mode": mode,
                "image_path": str(image_path),
                "image_name": row.get("image_name", ""),
                "region_name": region_name,
                "region_box": "",
                "status": "not_run",
                "char_count": 0,
                "error": "",
                "started_at": started_at,
                "finished_at": "",
            }
            try:
                if mode == "whole-image":
                    text = ocr_whole_image(image_path)
                else:
                    text, region_box = ocr_region(image_path, region_name)
                    rec["region_box"] = region_box
                rec["status"] = "complete"
                rec["text"] = text
                rec["char_count"] = len(text.strip())
            except Exception as exc:
                rec["status"] = "failed"
                rec["text"] = ""
                rec["error"] = repr(exc)
                error_rows.append({k: rec.get(k, "") for k in ["run_key", "batch_id", "mode", "image_path", "image_name", "region_name", "status", "error", "started_at"]})
            rec["finished_at"] = datetime.now(timezone.utc).isoformat()
            json_records.append(rec)
            ledger_rows.append({k: rec.get(k, "") for k in ["run_key", "batch_id", "mode", "image_path", "image_name", "region_name", "status", "char_count", "error", "started_at", "finished_at"]})

    with jsonl_path.open("a", encoding="utf-8") as f:
        for rec in json_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    ledger_fields = ["run_key", "batch_id", "mode", "image_path", "image_name", "region_name", "status", "char_count", "error", "started_at", "finished_at"]
    append_csv(ledger_path, ledger_rows, ledger_fields)
    error_fields = ["run_key", "batch_id", "mode", "image_path", "image_name", "region_name", "status", "error", "started_at"]
    if error_rows:
        append_csv(error_queue_path, error_rows, error_fields)
    elif not error_queue_path.exists():
        append_csv(error_queue_path, [], error_fields)

    status_counts = Counter(r.get("status", "") for r in ledger_rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_plan": str(batch_plan),
        "batch_id": batch_id,
        "mode": mode,
        "planned_images": len(planned),
        "new_records": len(ledger_rows),
        "skipped_completed_records": sum(1 for r in planned for region in (["whole_image"] if mode == "whole-image" else list(REGION_FRACTIONS.keys())) if f"{batch_id}::{mode}::{Path(r.get('image_path', ''))}::{region}" in done),
        "status_counts": dict(status_counts),
        "ledger": str(ledger_path),
        "error_queue": str(error_queue_path),
        "jsonl": str(jsonl_path),
        "policy": "candidate_only_no_auto_confirmation",
    }
    status_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one FR24 OCR batch")
    parser.add_argument("--batch-plan", default="data/_manifests/fr24_audit/fr24_full_corpus_batch_plan.csv")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--mode", required=True, choices=sorted(VALID_MODES))
    parser.add_argument("--output-dir", default="data/_manifests/fr24_audit")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    run_batch(Path(args.batch_plan), args.batch_id, args.mode, Path(args.output_dir), args.limit)


if __name__ == "__main__":
    main()
