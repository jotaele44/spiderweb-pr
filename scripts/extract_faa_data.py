#!/usr/bin/env python3
"""Extract FAA Releasable Aircraft Registry records for a target N-number list.

Design goals:
- Use the FAA offline releasable database files, not demo fixtures.
- Produce one ledger row per requested N-number, including not_found rows.
- Fail loudly when expected counts or production-source gates are not satisfied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

FAA_MASTER_FIELDS = [
    "N-NUMBER", "SERIAL NUMBER", "MFR MDL CODE", "ENG MFR MDL", "YEAR MFR",
    "TYPE REGISTRANT", "NAME", "STREET", "STREET2", "CITY", "STATE", "ZIP CODE",
    "REGION", "COUNTY", "COUNTRY", "LAST ACTION DATE", "CERT ISSUE DATE",
    "CERTIFICATION", "TYPE AIRCRAFT", "TYPE ENGINE", "STATUS CODE", "MODE S CODE",
    "FRACT OWNER", "AIR WORTH DATE", "OTHER NAMES(1)", "OTHER NAMES(2)",
    "OTHER NAMES(3)", "OTHER NAMES(4)", "OTHER NAMES(5)", "EXPIRATION DATE",
    "UNIQUE ID", "KIT MFR", "KIT MODEL", "MODE S CODE HEX",
]

FAA_ACFTREF_FIELDS = [
    "CODE", "MFR", "MODEL", "TYPE-ACFT", "TYPE-ENG", "AC-CAT", "BUILD-CERT-IND",
    "NO-ENG", "NO-SEATS", "AC-WEIGHT", "SPEED",
]

FAA_ENGINE_FIELDS = ["CODE", "MFR", "MODEL", "TYPE", "HORSEPOWER", "THRUST"]

FAA_DEREG_FIELDS = [
    "N-NUMBER", "SERIAL-NUMBER", "MFR-MDL-CODE", "STATUS-CODE", "NAME", "STREET",
    "STREET2", "CITY", "STATE", "ZIP-CODE", "ENG-MFR-MDL", "YEAR-MFR", "CERTIFICATION",
    "REGION", "COUNTY", "COUNTRY", "AIR-WORTH-DATE", "CANCEL-DATE", "MODE-S-CODE",
    "INDICATOR-GROUP", "EXPIRATION-DATE", "TYPE-AIRCRAFT", "TYPE-ENGINE", "KIT-MFR",
    "KIT-MODEL", "MODE-S-CODE-HEX",
]

OUTPUT_FIELDS = [
    "registration", "query_key", "match_status", "source_file", "source_record_count",
    "source_row_number", "aircraft_mfr_model_code", "manufacturer", "model", "serial_number",
    "year_manufactured", "type_aircraft", "type_engine", "engine_mfr_model_code",
    "engine_manufacturer", "engine_model", "owner", "street1", "street2", "city", "state",
    "zipcode", "country", "region", "county", "status_code", "certification", "cert_issue_date",
    "air_worth_date", "last_action_date", "expiration_date", "cancel_date", "mode_s_code",
    "mode_s_code_hex", "unique_id", "conflict_flag", "conflict_notes", "confidence",
]


def normalize_header(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (value or "").strip().upper()).strip("_")


def get_any(row: Dict[str, str], names: Sequence[str], default: str = "") -> str:
    for name in names:
        keys = {name, name.upper(), name.lower(), normalize_header(name)}
        for key in keys:
            if key in row and str(row[key]).strip() != "":
                return str(row[key]).strip()
    return default


def normalize_n_key(value: str) -> str:
    raw = (value or "").strip().upper()
    raw = raw.replace(" ", "").replace("-", "")
    raw = re.sub(r"[^A-Z0-9]", "", raw)
    if raw.startswith("N"):
        raw = raw[1:]
    return raw


def display_n(key: str) -> str:
    key = normalize_n_key(key)
    return f"N{key}" if key else ""


def parse_date_key(value: str) -> str:
    """Return sortable YYYYMMDD-ish key for FAA date strings; blanks sort low."""
    raw = re.sub(r"[^0-9]", "", value or "")
    if len(raw) == 8:
        # Handles YYYYMMDD or MMDDYYYY. FAA commonly stores MMDDYYYY in some files.
        first4 = int(raw[:4])
        if 1900 <= first4 <= 2100:
            return raw
        return raw[4:] + raw[:4]
    if len(raw) == 6:
        return "20" + raw if int(raw[:2]) < 50 else "19" + raw
    return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_file(faa_dir: Path, candidates: Sequence[str]) -> Optional[Path]:
    lower = {c.lower() for c in candidates}
    for p in faa_dir.rglob("*"):
        if p.is_file() and p.name.lower() in lower:
            return p
    return None


def sniff_has_header(path: Path, expected_first_names: Sequence[str]) -> bool:
    with path.open("r", encoding="latin-1", newline="", errors="replace") as f:
        sample = f.readline()
    cells = [normalize_header(c) for c in next(csv.reader([sample]))]
    expected = {normalize_header(n) for n in expected_first_names}
    return bool(cells and cells[0] in expected)


def iter_csv_rows(path: Path, fallback_fields: Sequence[str]) -> Iterable[Tuple[int, Dict[str, str]]]:
    has_header = sniff_has_header(path, fallback_fields[:3])
    with path.open("r", encoding="latin-1", newline="", errors="replace") as f:
        if has_header:
            reader = csv.DictReader(f)
            assert reader.fieldnames is not None
            normalized_fieldnames = [normalize_header(x) for x in reader.fieldnames]
            for row_number, row in enumerate(reader, start=2):
                normalized = {normalize_header(k): (v or "").strip() for k, v in row.items() if k is not None}
                # Retain original-ish keys for get_any fallback.
                normalized.update({k: (v or "").strip() for k, v in row.items() if k is not None})
                yield row_number, normalized
        else:
            reader = csv.reader(f)
            fields = [normalize_header(x) for x in fallback_fields]
            for row_number, cells in enumerate(reader, start=1):
                if not cells or all(not c.strip() for c in cells):
                    continue
                if len(cells) < len(fields):
                    cells = cells + [""] * (len(fields) - len(cells))
                row = {fields[i]: cells[i].strip() for i in range(min(len(fields), len(cells)))}
                yield row_number, row


def load_registrations(path: Path) -> Tuple[List[str], List[str]]:
    if not path.exists():
        raise FileNotFoundError(f"registration input file not found: {path}")
    ordered: "OrderedDict[str, None]" = OrderedDict()
    rejected: List[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        token = line.strip().split(",")[0].strip()
        if not token or token.startswith("#"):
            continue
        key = normalize_n_key(token)
        if key:
            ordered[key] = None
        else:
            rejected.append(line)
    return list(ordered.keys()), rejected


def load_reference(path: Optional[Path], fields: Sequence[str]) -> Dict[str, Dict[str, str]]:
    if not path or not path.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for _, row in iter_csv_rows(path, fields):
        code = get_any(row, ["CODE"])
        if code:
            out[code.strip()] = row
    return out


def choose_best_record(records: List[Dict[str, str]]) -> Dict[str, str]:
    if len(records) == 1:
        return records[0]
    def score(row: Dict[str, str]) -> Tuple[str, str, int]:
        date = max(
            parse_date_key(get_any(row, ["LAST ACTION DATE", "LAST_ACTION_DATE"])),
            parse_date_key(get_any(row, ["EXPIRATION DATE", "EXPIRATION_DATE", "EXPIRATION-DATE"])),
            parse_date_key(get_any(row, ["CERT ISSUE DATE", "CERT_ISSUE_DATE"])),
        )
        active_bonus = "1" if get_any(row, ["STATUS CODE", "STATUS_CODE", "STATUS-CODE"]).upper() in {"V", "A", ""} else "0"
        filled = sum(1 for v in row.values() if str(v).strip())
        return (active_bonus, date, filled)
    return sorted(records, key=score, reverse=True)[0]


def conflict_notes(records: List[Dict[str, str]]) -> Tuple[str, str]:
    if len(records) <= 1:
        return "false", ""
    watched = ["NAME", "STREET", "CITY", "STATE", "ZIP CODE", "STATUS CODE", "EXPIRATION DATE"]
    notes = []
    for field in watched:
        vals = sorted({get_any(r, [field, field.replace(" ", "_"), field.replace(" ", "-")]) for r in records if get_any(r, [field, field.replace(" ", "_"), field.replace(" ", "-")])})
        if len(vals) > 1:
            notes.append(f"{field}:" + "|".join(vals[:4]))
    return ("true" if notes else "false", "; ".join(notes))


def build_output_row(
    key: str,
    records: List[Dict[str, str]],
    source_file: str,
    acft_ref: Dict[str, Dict[str, str]],
    eng_ref: Dict[str, Dict[str, str]],
    status: str,
) -> Dict[str, str]:
    if not records:
        row = {f: "" for f in OUTPUT_FIELDS}
        row.update({
            "registration": display_n(key), "query_key": key, "match_status": "not_found",
            "source_file": "", "source_record_count": "0", "confidence": "0.00",
        })
        return row

    best = choose_best_record(records)
    mfr_code = get_any(best, ["MFR MDL CODE", "MFR_MDL_CODE", "MFR-MDL-CODE"])
    eng_code = get_any(best, ["ENG MFR MDL", "ENG_MFR_MDL", "ENG-MFR-MDL"])
    acft = acft_ref.get(mfr_code, {})
    eng = eng_ref.get(eng_code, {})
    cflag, cnotes = conflict_notes(records)

    out = {f: "" for f in OUTPUT_FIELDS}
    out.update({
        "registration": display_n(key),
        "query_key": key,
        "match_status": status,
        "source_file": source_file,
        "source_record_count": str(len(records)),
        "source_row_number": get_any(best, ["__ROW_NUMBER"]),
        "aircraft_mfr_model_code": mfr_code,
        "manufacturer": get_any(acft, ["MFR"]),
        "model": get_any(acft, ["MODEL"]),
        "serial_number": get_any(best, ["SERIAL NUMBER", "SERIAL_NUMBER", "SERIAL-NUMBER"]),
        "year_manufactured": get_any(best, ["YEAR MFR", "YEAR_MFR", "YEAR-MFR"]),
        "type_aircraft": get_any(best, ["TYPE AIRCRAFT", "TYPE_AIRCRAFT", "TYPE-AIRCRAFT"]),
        "type_engine": get_any(best, ["TYPE ENGINE", "TYPE_ENGINE", "TYPE-ENGINE"]),
        "engine_mfr_model_code": eng_code,
        "engine_manufacturer": get_any(eng, ["MFR"]),
        "engine_model": get_any(eng, ["MODEL"]),
        "owner": get_any(best, ["NAME"]),
        "street1": get_any(best, ["STREET"]),
        "street2": get_any(best, ["STREET2"]),
        "city": get_any(best, ["CITY"]),
        "state": get_any(best, ["STATE"]),
        "zipcode": get_any(best, ["ZIP CODE", "ZIP_CODE", "ZIP-CODE"]),
        "country": get_any(best, ["COUNTRY"]),
        "region": get_any(best, ["REGION"]),
        "county": get_any(best, ["COUNTY"]),
        "status_code": get_any(best, ["STATUS CODE", "STATUS_CODE", "STATUS-CODE"]),
        "certification": get_any(best, ["CERTIFICATION"]),
        "cert_issue_date": get_any(best, ["CERT ISSUE DATE", "CERT_ISSUE_DATE"]),
        "air_worth_date": get_any(best, ["AIR WORTH DATE", "AIR_WORTH_DATE", "AIR-WORTH-DATE"]),
        "last_action_date": get_any(best, ["LAST ACTION DATE", "LAST_ACTION_DATE"]),
        "expiration_date": get_any(best, ["EXPIRATION DATE", "EXPIRATION_DATE", "EXPIRATION-DATE"]),
        "cancel_date": get_any(best, ["CANCEL DATE", "CANCEL_DATE", "CANCEL-DATE"]),
        "mode_s_code": get_any(best, ["MODE S CODE", "MODE_S_CODE", "MODE-S-CODE"]),
        "mode_s_code_hex": get_any(best, ["MODE S CODE HEX", "MODE_S_CODE_HEX", "MODE-S-CODE-HEX"]),
        "unique_id": get_any(best, ["UNIQUE ID", "UNIQUE_ID"]),
        "conflict_flag": cflag,
        "conflict_notes": cnotes,
        "confidence": "0.99" if status == "matched" else "0.85",
    })
    return out


def index_records(path: Optional[Path], target_keys: set, fallback_fields: Sequence[str]) -> Dict[str, List[Dict[str, str]]]:
    indexed: Dict[str, List[Dict[str, str]]] = {k: [] for k in target_keys}
    if not path or not path.exists():
        return indexed
    for row_number, row in iter_csv_rows(path, fallback_fields):
        key = normalize_n_key(get_any(row, ["N-NUMBER", "N NUMBER", "N_NUMBER", "N-NUM", "NNUM"] ))
        if key in target_keys:
            row["__ROW_NUMBER"] = str(row_number)
            indexed.setdefault(key, []).append(row)
    return indexed


def write_outputs(rows: List[Dict[str, str]], output: Path, manifest: Dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    report_path = output.with_suffix(output.suffix + ".validation.md")
    lines = [
        "# FAA Registry Extraction Validation Report",
        "",
        f"Run timestamp: `{manifest['run_timestamp']}`",
        f"Input registrations: `{manifest['input_unique_count']}`",
        f"Output ledger rows: `{manifest['output_rows']}`",
        f"Matched: `{manifest['matched_count']}`",
        f"Deregistered: `{manifest['deregistered_count']}`",
        f"Not found: `{manifest['not_found_count']}`",
        f"Ledger coverage: `{manifest['ledger_coverage_pct']:.2f}%`",
        f"Match rate: `{manifest['match_rate_pct']:.2f}%`",
        "",
        "## Source files",
    ]
    for name, meta in manifest.get("source_files", {}).items():
        if isinstance(meta, dict):
            lines.append(f"- `{name}`: `{meta.get('path','')}` bytes=`{meta.get('bytes','')}` sha256=`{str(meta.get('sha256',''))[:16]}...`")
    lines.extend(["", "## Status counts", ""])
    counts = OrderedDict()
    for r in rows:
        counts[r["match_status"]] = counts.get(r["match_status"], 0) + 1
    for k, v in counts.items():
        lines.append(f"- `{k}`: `{v}`")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract FAA registry records for target N-numbers.")
    parser.add_argument("--registrations", required=True, help="Text/CSV file containing target N-numbers, one per line or first CSV column.")
    parser.add_argument("--faa-dir", required=True, help="Directory containing FAA ReleasableAircraft extracted files.")
    parser.add_argument("--output", required=True, help="Output consolidated CSV path.")
    parser.add_argument("--expected-count", type=int, default=None, help="Expected unique input registration count; fail if mismatch.")
    parser.add_argument("--fail-under-coverage", type=float, default=1.0, help="Minimum output ledger coverage ratio versus expected/input count.")
    parser.add_argument("--no-demo", action="store_true", help="Reject tiny/demo FAA source files and fixture-like paths.")
    parser.add_argument("--min-master-bytes", type=int, default=1_000_000, help="Minimum MASTER file size when --no-demo is set.")
    args = parser.parse_args(argv)

    regs_path = Path(args.registrations)
    faa_dir = Path(args.faa_dir)
    output = Path(args.output)

    if not faa_dir.exists():
        raise FileNotFoundError(f"FAA directory not found: {faa_dir}")

    keys, rejected = load_registrations(regs_path)
    if not keys:
        raise RuntimeError(f"No valid registrations found in {regs_path}")
    if args.expected_count is not None and len(keys) != args.expected_count:
        raise RuntimeError(f"Input count gate failed: expected {args.expected_count}, found {len(keys)} unique normalized registrations in {regs_path}")

    master = find_file(faa_dir, ["MASTER.txt", "MASTER.CSV"])
    dereg = find_file(faa_dir, ["DEREG.txt", "DEREG.CSV"])
    acftref = find_file(faa_dir, ["ACFTREF.txt", "ACFTREF.CSV"])
    engine = find_file(faa_dir, ["ENGINE.txt", "ENGINE.CSV"])
    if not master:
        raise FileNotFoundError(f"Could not find MASTER.txt under {faa_dir}")

    if args.no_demo:
        suspicious = any(part.lower() in {"fixture", "fixtures", "demo", "sample", "testdata"} for part in master.parts)
        if suspicious:
            raise RuntimeError(f"Demo-block gate failed: MASTER path looks like fixture/demo data: {master}")
        if master.stat().st_size < args.min_master_bytes:
            raise RuntimeError(f"Source-size gate failed: {master} is only {master.stat().st_size} bytes; this looks like a fixture, not the FAA production MASTER.txt")

    target = set(keys)
    acft_ref = load_reference(acftref, FAA_ACFTREF_FIELDS)
    eng_ref = load_reference(engine, FAA_ENGINE_FIELDS)
    master_index = index_records(master, target, FAA_MASTER_FIELDS)
    dereg_index = index_records(dereg, target, FAA_DEREG_FIELDS) if dereg else {k: [] for k in target}

    rows: List[Dict[str, str]] = []
    for key in keys:
        if master_index.get(key):
            rows.append(build_output_row(key, master_index[key], master.name, acft_ref, eng_ref, "matched"))
        elif dereg_index.get(key):
            rows.append(build_output_row(key, dereg_index[key], dereg.name if dereg else "DEREG.txt", acft_ref, eng_ref, "deregistered"))
        else:
            rows.append(build_output_row(key, [], "", acft_ref, eng_ref, "not_found"))

    expected = args.expected_count or len(keys)
    ledger_coverage = len(rows) / expected if expected else 0.0
    if ledger_coverage < args.fail_under_coverage:
        raise RuntimeError(f"Coverage gate failed: rows={len(rows)} expected={expected} coverage={ledger_coverage:.2%} threshold={args.fail_under_coverage:.2%}")

    matched_count = sum(1 for r in rows if r["match_status"] == "matched")
    dereg_count = sum(1 for r in rows if r["match_status"] == "deregistered")
    not_found_count = sum(1 for r in rows if r["match_status"] == "not_found")

    source_files = {}
    for label, path in {"master": master, "deregistered": dereg, "aircraft_reference": acftref, "engine_reference": engine}.items():
        if path and path.exists():
            source_files[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}

    manifest = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "registrations_file": str(regs_path),
        "faa_dir": str(faa_dir),
        "output_csv": str(output),
        "input_unique_count": len(keys),
        "rejected_input_lines": rejected,
        "expected_count": expected,
        "output_rows": len(rows),
        "matched_count": matched_count,
        "deregistered_count": dereg_count,
        "not_found_count": not_found_count,
        "ledger_coverage_pct": ledger_coverage * 100,
        "match_rate_pct": (matched_count / len(keys) * 100) if keys else 0.0,
        "source_files": source_files,
    }
    write_outputs(rows, output, manifest)
    print(json.dumps({
        "status": "ok",
        "output": str(output),
        "manifest": str(output) + ".manifest.json",
        "validation_report": str(output) + ".validation.md",
        "input_unique_count": len(keys),
        "output_rows": len(rows),
        "matched_count": matched_count,
        "deregistered_count": dereg_count,
        "not_found_count": not_found_count,
        "ledger_coverage_pct": round(ledger_coverage * 100, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
