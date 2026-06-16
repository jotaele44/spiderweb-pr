#!/usr/bin/env python3
"""
Shared contract for every missing-persons harvester (phase 2a).

Every per-source harvester under ``scripts/<source>_harvest.py`` writes the
SAME canonical CSV schema — see ``CANONICAL_COLUMNS`` below — so the
consolidator (phase 2b: ``scripts/consolidate_missing_persons.py``) can read
any per-source canonical without per-source branching.

A concrete harvester subclasses ``HarvestBase`` and provides:

  * ``SOURCE_ID``        — short slug, matches the registry key in
                           ``configs/missing_persons_sources.yaml`` and the
                           ``source_id`` column of every emitted row.
  * ``SOURCE_STRATUM``   — "A" (confirmed/structured), "B" (confirmed/narrative),
                           or "C" (tip-stream — never federation-eligible).
  * ``SOURCE_DIR_NAME``  — subdirectory under ``data/sources/`` to look for
                           dated snapshots in. Default: ``cls.SOURCE_ID``.
  * ``RAW_FILENAME``     — name of the per-snapshot raw input file. Default:
                           ``f"{cls.SOURCE_ID}_pr.csv"``.
  * ``RAW_ALIASES``      — dict of canonical_field → list of accepted raw
                           header names. The first match wins.
  * ``normalize_row``    — instance method, takes one raw row + the snapshot
                           date, returns one canonical dict (or ``None`` to
                           drop). The base ``redact_rows`` loop calls this.

The base class enforces the PII boundary: name / DOB / photo / narrative fields
are dropped at the row level by virtue of NOT appearing in ``CANONICAL_COLUMNS``.
A subclass that adds a name to the canonical breaks the contract by
construction.

Stdlib only. No dependency on yaml, requests, or geopandas.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# The v2 extended canonical. Mirrored verbatim in:
#   - scripts/namus_harvest.py:CANONICAL_COLUMNS
#   - tools/pr_geodata_integrity_audit.py:NAMUS_CANONICAL_COLUMNS
# Any change here must be reflected in both, plus a migration note in
# data/sources/<source>/README.md for each landed harvester.
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

VALID_STRATA = {"A", "B", "C"}

VALID_INCIDENT_CLASSES = {
    "missing_juvenile",
    "missing_adult_woman",
    "missing_adult_other",
    "endangered_woman",         # PRPB Plan ROSA, Observatorio femicide-adjacent
    "cognitive_impairment",     # PRPB Plan SILVER
    "endangered_adult",         # PRPB Plan ASHANTI
    "maritime",                 # IOM Missing Migrants
    "disaster",                 # backfill module (María/Fiona/2020 earthquake)
    "unidentified_remains",     # NamUs Unidentified stream, ICF
    "unclaimed_decedent",       # NamUs Unclaimed stream
    "international_missing",    # Interpol Yellow Notices
}


def validate_incident_class(value: str) -> str:
    """Raise if ``value`` is a non-empty incident_class outside the closed
    vocabulary. Every harvester calls this on the value it is about to write,
    so a typo'd class constant in a new harvester fails loudly at harvest time
    instead of silently corrupting the canonical CSV.

    The original design routed this through HarvestBase.redact_rows, but the
    shipping harvesters bypass that method (NamUs has its own redact_rows; the
    PRPB harvesters override harvest() and call normalize_row directly), so the
    guard was unreachable. Call this directly from each normalize_row /
    redact_rows instead — the path that actually runs."""
    if value and value not in VALID_INCIDENT_CLASSES:
        raise ValueError(
            f"unknown incident_class {value!r}; add it to VALID_INCIDENT_CLASSES "
            f"in scripts/_harvest_base.py before emitting it."
        )
    return value


# ---------------------------------------------------------------- normalization
# Shared normalizers. Subclasses MAY override but rarely need to — every
# missing-persons source uses some flavor of the same status/age/sex axes.

STATUS_NORMALIZATION = {
    "missing": "active",
    "active": "active",
    "open": "active",
    "unresolved": "active",
    "resolved – alive": "resolved_alive",
    "resolved alive": "resolved_alive",
    "located alive": "resolved_alive",
    "located": "resolved_alive",
    "found alive": "resolved_alive",
    "resolved – deceased": "resolved_deceased",
    "resolved deceased": "resolved_deceased",
    "located deceased": "resolved_deceased",
    "found deceased": "resolved_deceased",
    "deceased": "resolved_deceased",
    "cold": "cold",
    "cold case": "cold",
}


def hash_id(raw: str, n: int = 12) -> str:
    """SHA-256 prefix hash. Empty input → empty string (never a fake hash)."""
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:n]


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


def coerce_coord(raw: Any) -> Optional[float]:
    if raw in (None, ""):
        return None
    try:
        return round(float(raw), 6)
    except (TypeError, ValueError):
        return None


# Coarse ethnicity bands. Substring match on lowercased raw value; first wins.
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


def bucket_ethnicity(raw: str) -> str:
    if not raw:
        return ""
    low = raw.lower()
    for token, band in ETHNICITY_BANDS:
        if token in low:
            return band
    return "unknown"


def empty_canonical(snapshot_date: str, source_id: str) -> Dict[str, str]:
    """Pre-filled dict with every canonical column present and empty. Use this
    so subclasses can't accidentally drop a column by forgetting it — the
    schema-drift check in the audit catches missing columns immediately."""
    row = {col: "" for col in CANONICAL_COLUMNS}
    row["source_id"] = source_id
    row["snapshot_date"] = snapshot_date
    return row


# ---------------------------------------------------------------- snapshot disco

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
    """Most recent dated subdir under ``sources_dir`` (ISO date convention).
    Malformed names that don't parse as a real date are skipped."""
    if not sources_dir.exists():
        return None
    candidates = sorted(
        (p for p in sources_dir.iterdir()
         if p.is_dir() and _is_iso_date_name(p.name)),
        reverse=True,
    )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------- the base

class HarvestBase:
    """Subclass and set the four class attributes + override ``normalize_row``."""

    SOURCE_ID: str = ""
    SOURCE_STRATUM: str = "A"
    SOURCE_DIR_NAME: str = ""        # default: SOURCE_ID
    RAW_FILENAME: str = ""           # default: f"{SOURCE_ID}_pr.csv"
    RAW_ALIASES: Dict[str, List[str]] = {}

    @classmethod
    def sources_dir(cls) -> Path:
        return REPO_ROOT / "data" / "sources" / (cls.SOURCE_DIR_NAME or cls.SOURCE_ID)

    @classmethod
    def raw_filename(cls) -> str:
        return cls.RAW_FILENAME or f"{cls.SOURCE_ID}_pr.csv"

    @classmethod
    def canonical_filename(cls) -> str:
        return f"{cls.SOURCE_ID}_pr_canonical.csv"

    @classmethod
    def pick(cls, row: Dict[str, str], key: str) -> str:
        """First-non-empty value among the aliases for ``key``."""
        for alias in cls.RAW_ALIASES.get(key, []):
            value = row.get(alias)
            if value is None:
                continue
            value = value.strip()
            if value:
                return value
        return ""

    # --- subclass overrides ------------------------------------------------

    def normalize_row(self, raw: Dict[str, str], snapshot_date: str) -> Optional[Dict[str, str]]:
        """Take a raw CSV row dict, return a canonical dict matching
        ``CANONICAL_COLUMNS`` exactly, or return ``None`` to drop the row.

        Subclasses typically:
            1. ``row = empty_canonical(snapshot_date, self.SOURCE_ID)``
            2. populate the fields the source carries
            3. drop names / photos / narrative — they're not in ``row`` keys
               so they're already gone
            4. compute ``incident_class`` per source semantics
            5. return ``row``
        """
        raise NotImplementedError

    # --- harvest loop ------------------------------------------------------

    def redact_rows(self, raw_rows: List[Dict[str, str]], snapshot_date: str) -> Tuple[List[Dict[str, str]], int]:
        out: List[Dict[str, str]] = []
        dropped = 0
        for raw in raw_rows:
            canonical = self.normalize_row(raw, snapshot_date)
            if canonical is None:
                dropped += 1
                continue
            # Self-checks: subclass mistakes caught here, not at the audit.
            missing = set(CANONICAL_COLUMNS) - set(canonical.keys())
            assert not missing, f"{self.SOURCE_ID} normalize_row dropped columns: {missing}"
            extra = set(canonical.keys()) - set(CANONICAL_COLUMNS)
            assert not extra, f"{self.SOURCE_ID} normalize_row added unknown columns: {extra}"
            if canonical["incident_class"] and canonical["incident_class"] not in VALID_INCIDENT_CLASSES:
                raise ValueError(
                    f"{self.SOURCE_ID} emitted unknown incident_class "
                    f"{canonical['incident_class']!r}; add it to VALID_INCIDENT_CLASSES "
                    f"in scripts/_harvest_base.py first."
                )
            out.append(canonical)
        return out, dropped

    def write_canonical(self, rows: List[Dict[str, str]], path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def harvest(self, snapshot_dir: Path) -> Tuple[Path, int, int]:
        raw_path = snapshot_dir / self.raw_filename()
        if not raw_path.exists():
            raise FileNotFoundError(f"Expected raw {self.SOURCE_ID} CSV at {raw_path}")
        snapshot_date = snapshot_dir.name
        with raw_path.open(encoding="utf-8-sig") as fh:
            raw_rows = list(csv.DictReader(fh))
        canonical, dropped = self.redact_rows(raw_rows, snapshot_date)
        out_path = snapshot_dir / self.canonical_filename()
        self.write_canonical(canonical, out_path)
        return out_path, len(canonical), dropped

    # --- main() shim that subclasses can call from their __main__ ----------

    def main(self, argv: Optional[List[str]] = None) -> int:
        parser = argparse.ArgumentParser(
            description=f"{self.SOURCE_ID} missing-persons harvester (stratum {self.SOURCE_STRATUM})."
        )
        parser.add_argument("--sources-dir", type=Path, default=self.sources_dir(),
                            help="Directory containing dated snapshot subdirs.")
        parser.add_argument("--snapshot", type=str, default=None,
                            help="Specific snapshot date (YYYY-MM-DD).")
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
                print(f"ERROR: no dated snapshot subdir under {sources_dir}.", file=sys.stderr)
                return 2

        out_path, kept, dropped = self.harvest(snapshot_dir)
        try:
            display = out_path.relative_to(REPO_ROOT)
        except ValueError:
            display = out_path
        print(f"{self.SOURCE_ID}_harvest: snapshot={snapshot_dir.name} "
              f"kept={kept} dropped={dropped} -> {display}")
        return 0
