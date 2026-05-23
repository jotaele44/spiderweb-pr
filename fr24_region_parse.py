"""
FR24 REGION OCR PARSER

Parses region OCR JSONL output into structured candidate records. The parser is
region-aware, but conservative: all extracted fields are candidates and require
review before use as facts.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, List

PARSER_VERSION = "fr24_region_parse_v0.1.1"


def clean(text: str) -> str:
    return " ".join((text or "").split())


def find_first(patterns: Iterable[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip()
    return ""


def extract_status(record: dict) -> str:
    """Normalize region OCR status from probe JSONL or batch-run JSONL.

    fr24_region_ocr.py writes extract_status, while fr24_batch_run.py writes
    status. Both represent the same candidate extraction state for this parser.
    """
    return record.get("extract_status") or record.get("status") or ""


def extract_airport_codes(text: str) -> tuple[str, str]:
    codes = re.findall(r"\b(BQN|SJU|PSE|SIG|NRR|NIP|NUW|CPX|EIS|PBI|MAZ|ARE|MIA|JFK|EWR|ATL|MCO|TPA|FLL)\b", text)
    origin = codes[0] if codes else ""
    destination = codes[1] if len(codes) > 1 else ""
    return origin, destination


def confidence_score(row: dict) -> float:
    score = 0.0
    if row.get("fr24_detected") == "true":
        score += 0.12
    if row.get("callsign_or_label"):
        score += 0.16
    if row.get("operator"):
        score += 0.12
    if row.get("aircraft_type"):
        score += 0.14
    if row.get("registration"):
        score += 0.14
    if row.get("barometric_altitude_ft"):
        score += 0.10
    if row.get("ground_speed_mph"):
        score += 0.10
    if row.get("playback_date") or row.get("playback_time"):
        score += 0.12
    if row.get("region_name") == "right_panel" and (row.get("registration") or row.get("aircraft_type")):
        score += 0.05
    if row.get("region_name") == "bottom_timeline" and (row.get("playback_date") or row.get("playback_time")):
        score += 0.05
    return round(min(score, 1.0), 2)


def parse_region_record(record: dict) -> dict:
    text = clean(record.get("text", ""))
    region_name = record.get("region_name", "")
    status = extract_status(record)
    try:
        char_count = int(record.get("char_count") or 0)
    except Exception:
        char_count = 0

    row = {
        "candidate_id": f"region::{Path(record.get('image_path', '')).name}::{region_name}",
        "image_path": record.get("image_path", ""),
        "image_name": record.get("image_name", ""),
        "sidecar_title": record.get("sidecar_title", ""),
        "match_band": record.get("match_band", ""),
        "source_review_status": record.get("source_review_status", ""),
        "region_name": region_name,
        "region_box": record.get("region_box", ""),
        "extract_status": status,
        "char_count": char_count,
        "fr24_detected": "true" if re.search(r"flight\s*radar|flightradar24|flighttadar|flightiadar|glightradar", text, re.I) else "false",
        "callsign_or_label": "",
        "operator": "",
        "aircraft_type": "",
        "registration": "",
        "origin_code": "",
        "destination_code": "",
        "barometric_altitude_ft": "",
        "ground_speed_mph": "",
        "flight_status": "",
        "elapsed_departed": "",
        "elapsed_arrived": "",
        "playback_date": "",
        "playback_time": "",
        "playback_timezone": "",
        "confidence": 0,
        "review_status": "region_review_required",
        "parser_version": PARSER_VERSION,
        "ocr_text_excerpt": text[:700],
    }

    if row["extract_status"] != "complete":
        row["review_status"] = "region_ocr_failed"
        return row

    row["registration"] = find_first([r"\bREG\.?\s+([A-Z0-9\-]+)", r"\bREG\s+([A-Z0-9\-]+)", r"\b(N[0-9A-Z]{2,6})\b"], text)
    if row["registration"] in {"N", "NO", "N/A"}:
        row["registration"] = ""

    row["barometric_altitude_ft"] = find_first([r"BAROMETRIC ALT\.?.{0,100}?([0-9,]+)\s*ft", r"\b([0-9,]+)\s*ft\s+GROUND SPEED"], text)
    row["ground_speed_mph"] = find_first([r"GROUND SPEED.{0,100}?([0-9]+)\s*mph", r"\b([0-9]+)\s*mph\b"], text)
    row["elapsed_departed"] = find_first([r"Departed\s+([0-9:]+)\s*ago", r"\.\.\.parted\s+([0-9:]+)\s*ago"], text)
    row["elapsed_arrived"] = find_first([r"Arrived\s+([0-9:]+)\s*ago", r"Arrived([0-9:]+)\s*ago"], text)

    dt = re.search(
        r"\b((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+[A-Z][a-z]{2}\s+\d{1,2},\s+20\d{2})\s*\|\s*([0-9:]+)\s*([AP]M)?\s*u?T?C?\s*(-04:00)?",
        text,
        flags=re.I,
    )
    if dt:
        row["playback_date"] = dt.group(1)
        row["playback_time"] = " ".join(x for x in [dt.group(2), dt.group(3) or ""] if x)
        row["playback_timezone"] = dt.group(4) or ""

    row["callsign_or_label"] = find_first([
        r"\b([A-Z0-9]{3,10})\s+\([A-Z0-9]{2,5}\)",
        r"\b([A-Z]{2,}[A-Z0-9]{1,6})\s+(?:United States|Private owner|NetJets|Puerto Rico)",
        r"\b(N[0-9A-Z]{2,6})\s+\(",
    ], text)

    row["operator"] = find_first([
        r"\)\s+([A-Za-z0-9 \-\.]+?)\s+(?:BQN|SJU|PSE|SIG|NRR|N/A|BAROMETRIC)",
        r"\b(United States\s+-\s+[A-Za-z ]+)",
        r"\b(Private owner)",
        r"\b(Puerto Rico Electric Power Auth\.?\.\.?)",
        r"\b(NetJets)",
    ], text)

    row["aircraft_type"] = find_first([
        r"\b(Sikorsky MH-?60T Jayhawk)",
        r"\b(Lockheed Martin C-?130J-?30 Super [A-Za-z\. ]*)",
        r"\b(Lockheed C-?130T Hercules)",
        r"\b(Boeing C-?17A Globemaster III)",
        r"\b(Grumman C-?2A Greyhound)",
        r"\b(Airbus Helicopters H125)",
        r"\b(Airbus Helicopters H145)",
        r"\b(Airbus Helicopters H130)",
        r"\b(Bell 407)",
        r"\b(Bell 429 GlobalRanger)",
        r"\b(Robinson R44(?: Raven II)?)",
        r"\b(Cessna Citation Sovereign)",
        r"\b(McDonnell Douglas AV-8B\+? Harrier II)",
        r"\b(Leonardo AW109SP GrandNew)",
        r"\b(Bombardier E-11A)",
        r"\b(Icon A5)",
        r"\b(High Altitude Balloon)",
    ], text)

    origin, destination = extract_airport_codes(text)
    row["origin_code"] = origin
    row["destination_code"] = destination

    if row["elapsed_arrived"]:
        row["flight_status"] = "arrived_candidate"
    elif row["elapsed_departed"]:
        row["flight_status"] = "departed_candidate"
    elif "Arriving" in text or "Arrivingin" in text:
        row["flight_status"] = "arriving_candidate"

    row["confidence"] = confidence_score(row)
    if char_count < 20:
        row["review_status"] = "region_low_text_review"
    elif row["confidence"] >= 0.65:
        row["review_status"] = "region_parsed_candidate"
    else:
        row["review_status"] = "region_manual_review_required"
    return row


def parse_jsonl(input_jsonl: Path, output_csv: Path, review_csv: Path | None = None) -> dict:
    records: List[dict] = []
    with input_jsonl.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(parse_region_record(json.loads(line)))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if records:
        with output_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
    else:
        output_csv.write_text("", encoding="utf-8")

    review_records = [r for r in records if r["review_status"] != "region_parsed_candidate"]
    if review_csv:
        review_csv.parent.mkdir(parents=True, exist_ok=True)
        if records:
            with review_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
                writer.writeheader()
                writer.writerows(review_records)
        else:
            review_csv.write_text("", encoding="utf-8")

    summary = {
        "records": len(records),
        "review": len(review_records),
        "review_status": dict(Counter(r["review_status"] for r in records)),
        "regions": dict(Counter(r["region_name"] for r in records)),
        "fr24_detected": dict(Counter(r["fr24_detected"] for r in records)),
        "output_csv": str(output_csv),
        "review_csv": str(review_csv) if review_csv else "",
        "policy": "candidate_only_no_auto_confirmation",
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse FR24 region OCR JSONL into structured candidates")
    parser.add_argument("--input-jsonl", default="data/_manifests/fr24_audit/fr24_region_ocr_results.jsonl")
    parser.add_argument("--output-csv", default="data/_manifests/fr24_audit/fr24_region_parsed_events.csv")
    parser.add_argument("--review-csv", default="data/_manifests/fr24_audit/fr24_region_review_queue.csv")
    args = parser.parse_args()
    summary = parse_jsonl(Path(args.input_jsonl), Path(args.output_csv), Path(args.review_csv))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
