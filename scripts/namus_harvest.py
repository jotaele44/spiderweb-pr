#!/usr/bin/env python3
"""
NamUs Puerto Rico missing-persons harvester.

WHY THIS EXISTS
---------------
The National Missing and Unidentified Persons System (NamUs, US DOJ / NIJ) is
the authoritative public registry for missing-persons cases in US states and
territories, including Puerto Rico. There is no public bulk API; the export is
account-gated through namus.nij.ojp.gov. The operator pulls a CSV filtered to
State=Puerto Rico and drops it under:

    data/sources/namus/<YYYY-MM-DD>/namus_mp_pr.csv

This script reads that snapshot and writes a redacted canonical CSV next to it:

    data/sources/namus/<YYYY-MM-DD>/namus_mp_pr_canonical.csv

The redaction is non-recoverable. Names, photo URLs, full date-of-birth, and
free-text narrative ("Circumstances of Disappearance") are dropped at this
step — they never reach data/gis_layers/ or any federation export. The case
number is replaced with a 12-char SHA-256 prefix that is stable across runs
(so deduplication still works) but is not reversible without the original
file.

The canonical schema is the contract that
``scripts/populate_dataset_layers.py`` and ``tests/test_missing_persons_layer.py``
both depend on. Adding columns is safe; renaming or removing requires updating
both consumers.

Stdlib only. Safe to re-run; output is overwritten in place.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
DEFAULT_SOURCES_DIR = REPO_ROOT / "data" / "sources" / "namus"

# Single source of truth for the incident-class vocabulary lives in the shared
# harvest base. NamUs is standalone (predates _harvest_base) but reuses the
# validator so a future change to infer_incident_class can't emit an unknown
# class silently.
from scripts._harvest_base import validate_incident_class  # noqa: E402

# v2 extended canonical (phase 2a). Every column added since v1 is nullable so
# the v1 NamUs rows forward-migrate without surgery. The contract is shared
# across every per-source harvester (see scripts/_harvest_base.py).
SOURCE_ID = "namus"
SOURCE_STRATUM = "A"

CANONICAL_COLUMNS = [
    "case_id_hash",
    "source_id",
    "source_record_url_hash",
    "report_date",
    "last_seen_date",
    "found_date",
    "status",
    "status_reason",
    "age_band",
    "age_exact_known",
    "sex",
    "ethnicity_band",
    "last_seen_lat",
    "last_seen_lon",
    "last_seen_geocode_method",
    "last_seen_municipio",
    "last_seen_barrio",
    "circumstances_category",
    "circumstances_subcategory",
    "incident_class",
    "plan_match",
    "disaster_event_id",
    "linkage_keys_json",
    "coord_disagreement_km",
    "snapshot_date",
]

# NamUs raw column aliases. The public export header has shifted over time, so
# we accept the names we have seen rather than failing on a single canonical
# spelling. The first match wins.
RAW_ALIASES = {
    "case_number": ["Case Number", "Case ID", "CaseNumber", "case_number"],
    "case_url": ["Case URL", "URL", "Profile URL"],
    "report_date": ["Date Reported Missing", "Report Date", "DLC Date", "Reported"],
    "last_seen_date": ["Date Last Seen", "Last Seen", "DLS Date", "Last Contact"],
    "found_date": ["Date Located", "Date Found", "Resolution Date"],
    "status": ["Status", "Case Status"],
    "status_reason": ["Resolution", "Resolution Method", "Status Reason"],
    "age": ["Missing Age", "Age", "Age At Disappearance"],
    "sex": ["Sex", "Biological Sex", "Gender"],
    "race": ["Race / Ethnicity", "Race/Ethnicity", "Ethnicity", "Race"],
    "lat": ["Latitude", "Last Seen Latitude", "Lat"],
    "lon": ["Longitude", "Last Seen Longitude", "Lon"],
    "category": ["Category of Concern", "Circumstance Category", "Predictive Classification"],
    "subcategory": ["Circumstance Subcategory", "Sub-Category", "Subtype"],
}

# Coarse ethnicity bands. NamUs uses NIBRS-style labels; we bucket to 5 bands +
# Unknown so downstream stratification doesn't reidentify thin slices. Map is
# substring-based on lowercased raw value; first match wins.
ETHNICITY_BANDS = [
    ("hispanic", "hispanic_latino"),
    ("latino", "hispanic_latino"),
    ("latina", "hispanic_latino"),
    ("black", "black_afro"),
    ("african", "black_afro"),
    ("afro", "black_afro"),
    ("white", "white"),
    ("caucasian", "white"),
    ("asian", "asian"),
    ("native", "native"),
    ("american indian", "native"),
    ("indigenous", "native"),
    ("pacific", "native"),
    ("multi", "other"),
    ("biracial", "other"),
    ("other", "other"),
]

STATUS_NORMALIZATION = {
    "missing": "active",
    "active": "active",
    "open": "active",
    "unresolved": "active",
    "resolved missing": "active",
    "resolved – alive": "resolved_alive",
    "resolved alive": "resolved_alive",
    "located alive": "resolved_alive",
    "resolved – deceased": "resolved_deceased",
    "resolved deceased": "resolved_deceased",
    "located deceased": "resolved_deceased",
    "deceased": "resolved_deceased",
    "cold": "cold",
    "cold case": "cold",
}


def pick(row: Dict[str, str], key: str) -> str:
    """Return the first non-empty value among the aliases for ``key``."""
    for alias in RAW_ALIASES[key]:
        value = row.get(alias)
        if value is None:
            continue
        value = value.strip()
        if value:
            return value
    return ""


def hash_case_id(raw: str) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def bucket_age(raw: str) -> str:
    if not raw:
        return ""
    try:
        age = int(float(raw))
    except (TypeError, ValueError):
        return ""
    if age < 0:
        return ""
    if age <= 12:
        return "0_12"
    if age <= 17:
        return "13_17"
    if age <= 30:
        return "18_30"
    if age <= 50:
        return "31_50"
    return "51_plus"


def normalize_sex(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("m"):
        return "M"
    if s.startswith("f"):
        return "F"
    return "U"


def normalize_status(raw: str) -> str:
    s = (raw or "").strip().lower()
    return STATUS_NORMALIZATION.get(s, "active" if s else "")


def coerce_coord(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return round(float(raw), 6)
    except (TypeError, ValueError):
        return None


def bucket_ethnicity(raw: str) -> str:
    if not raw:
        return ""
    low = raw.lower()
    for token, band in ETHNICITY_BANDS:
        if token in low:
            return band
    return "unknown"


def infer_incident_class(age_band: str, sex: str, status: str) -> str:
    """NamUs Missing-Persons class inference. Resolution status does NOT change
    the class — a juvenile who was found deceased is still ``missing_juvenile``
    in this stream. The ``unidentified_remains`` / ``unclaimed_decedent``
    classes belong to the separate NamUs Unidentified and Unclaimed streams
    (phase 2d harvesters). Other harvesters override entirely — e.g., PRPB
    Alertas reads the alert plan directly into ``plan_match``."""
    if age_band in ("0_12", "13_17"):
        return "missing_juvenile"
    if sex == "F":
        return "missing_adult_woman"
    return "missing_adult_other"


def _is_iso_date_name(name: str) -> bool:
    """True only if ``name`` is a real ISO calendar date (YYYY-MM-DD). Guards
    against a malformed/typo'd snapshot dir ('9999-99-99', a year fat-finger)
    being lexicographically selected as the 'latest' over real dates."""
    if len(name) != 10 or name[4] != "-" or name[7] != "-":
        return False
    try:
        _dt.date.fromisoformat(name)
        return True
    except ValueError:
        return False


def latest_snapshot_dir(sources_dir: Path) -> Optional[Path]:
    if not sources_dir.exists():
        return None
    candidates = sorted(
        (p for p in sources_dir.iterdir() if p.is_dir() and _is_iso_date_name(p.name)),
        reverse=True,
    )
    return candidates[0] if candidates else None


def redact_rows(raw_rows: Iterable[Dict[str, str]], snapshot_date: str) -> Tuple[List[Dict[str, str]], int]:
    """Apply the redaction contract to every row. Drop rows with no case number."""
    out: List[Dict[str, str]] = []
    dropped_no_id = 0
    for row in raw_rows:
        raw_case = pick(row, "case_number")
        if not raw_case:
            dropped_no_id += 1
            continue
        age_raw = pick(row, "age")
        age_band = bucket_age(age_raw)
        sex = normalize_sex(pick(row, "sex"))
        status = normalize_status(pick(row, "status"))
        raw_lat = pick(row, "lat")
        raw_lon = pick(row, "lon")
        has_direct_coords = bool(raw_lat and raw_lon)
        canonical = {
            "case_id_hash": hash_case_id(raw_case),
            "source_id": SOURCE_ID,
            "source_record_url_hash": hash_case_id(pick(row, "case_url")),
            "report_date": pick(row, "report_date"),
            "last_seen_date": pick(row, "last_seen_date"),
            "found_date": pick(row, "found_date"),
            "status": status,
            "status_reason": pick(row, "status_reason"),
            "age_band": age_band,
            "age_exact_known": "true" if age_raw else "",
            "sex": sex,
            "ethnicity_band": bucket_ethnicity(pick(row, "race")),
            "last_seen_lat": coerce_coord(raw_lat) or "",
            "last_seen_lon": coerce_coord(raw_lon) or "",
            "last_seen_geocode_method": "direct" if has_direct_coords else "",
            # municipio/barrio populated downstream by the consolidator using
            # PIP against data/municipios.geojson and data/barrios.geojson —
            # NamUs's "City" column is unreliable for PR (often empty/English).
            "last_seen_municipio": "",
            "last_seen_barrio": "",
            "circumstances_category": pick(row, "category"),
            "circumstances_subcategory": pick(row, "subcategory"),
            "incident_class": validate_incident_class(infer_incident_class(age_band, sex, status)),
            "plan_match": "",  # NamUs doesn't map to PR alert plans
            "disaster_event_id": "",  # tagged later by backfill if applicable
            "linkage_keys_json": "",  # populated by consolidator
            "coord_disagreement_km": "",  # populated by consolidator
            "snapshot_date": snapshot_date,
        }
        out.append(canonical)
    return out, dropped_no_id


def write_canonical(rows: List[Dict[str, str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def harvest(snapshot_dir: Path) -> Tuple[Path, int, int]:
    raw_path = snapshot_dir / "namus_mp_pr.csv"
    if not raw_path.exists():
        raise FileNotFoundError(f"Expected raw NamUs CSV at {raw_path}")
    snapshot_date = snapshot_dir.name
    with raw_path.open(encoding="utf-8-sig") as fh:
        raw_rows = list(csv.DictReader(fh))
    canonical, dropped = redact_rows(raw_rows, snapshot_date)
    out_path = snapshot_dir / "namus_mp_pr_canonical.csv"
    write_canonical(canonical, out_path)
    return out_path, len(canonical), dropped


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip() if __doc__ else "")
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=DEFAULT_SOURCES_DIR,
        help=f"Directory containing dated NamUs snapshots. Default: {DEFAULT_SOURCES_DIR.relative_to(REPO_ROOT)}",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default=None,
        help="Specific snapshot date (YYYY-MM-DD). Default: most recent under --sources-dir.",
    )
    args = parser.parse_args(argv)

    sources_dir = args.sources_dir.resolve()
    if args.snapshot:
        snapshot_dir = sources_dir / args.snapshot
        if not snapshot_dir.is_dir():
            print(f"ERROR: snapshot dir not found: {snapshot_dir}", file=sys.stderr)
            return 2
    else:
        snapshot_dir = latest_snapshot_dir(sources_dir)
        if snapshot_dir is None:
            print(
                f"ERROR: no dated snapshot subdir under {sources_dir}. "
                f"Drop a CSV at <date>/namus_mp_pr.csv first.",
                file=sys.stderr,
            )
            return 2

    out_path, kept, dropped = harvest(snapshot_dir)
    try:
        display = out_path.relative_to(REPO_ROOT)
    except ValueError:
        display = out_path
    print(f"namus_harvest: snapshot={snapshot_dir.name} kept={kept} dropped_no_id={dropped} -> {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
