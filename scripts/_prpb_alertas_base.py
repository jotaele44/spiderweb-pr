#!/usr/bin/env python3
"""
Shared base for the four PRPB Alertas de Emergencia harvesters (phase 2c.1).

WHY ONE BASE
------------
PRPB runs four named emergency-alert plans (AMBER for kidnapped minors under
18; Plan ROSA for missing/kidnapped women 18+; Plan SILVER for persons with
cognitive impairment; Plan ASHANTI for missing/kidnapped adults 18+ in
dangerous circumstances). Every plan publishes per-incident HTML pages with
the same overall structure — date, age, sex, last-seen location, narrative.
The plan label is the only thing that varies. So we share the parser and let
each plan harvester be ~30 LOC: subclass, set ``SOURCE_ID`` + ``PLAN_MATCH`` +
``INCIDENT_CLASS``, and the rest is inherited.

OPERATOR MODEL
--------------
The harvester is *file-driven*, not network-driven. PRPB's site has no
robots-friendly position on automated scraping, so the operator pulls each
alert page manually (or via a one-off script with cautious rate limiting) and
saves them under::

    data/sources/prpb_alertas_<plan>/<YYYY-MM-DD>/<alert_id>.html

The harvester reads every ``*.html`` file in the latest dated snapshot dir,
extracts structured fields, drops names/photos, and emits the canonical CSV.

The parser is intentionally *defensive*: PRPB has changed page templates
before. The extraction uses regex over the visible text rather than DOM
selectors, so a template refresh that keeps the visible content stable
doesn't break us.

REDACTION
---------
Names visible on the page are NEVER extracted. The case_id_hash is derived
from the alert filename stem (which is operator-controlled — typically the
alert serial number that PRPB publishes alongside the page, e.g.
``ALERT-AMBER-2024-007.html``). Photo URLs are not retrieved.

Stdlib only.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts._harvest_base import (  # noqa: E402
    CANONICAL_COLUMNS,
    HarvestBase,
    bucket_age,
    bucket_ethnicity,
    coerce_coord,
    empty_canonical,
    hash_id,
    normalize_sex,
    normalize_status,
    validate_incident_class,
)
from scripts._text_extract_es import (  # noqa: E402
    extract_address,
    extract_age,
    extract_date,
    extract_municipio,
    extract_sex,
    extract_status,
    FIELD_CUES,
    match_after_cue,
)

# ---------------------------------------------------------------- HTML → text

class _TextExtractor(HTMLParser):
    """Strip tags, collect visible text segments. Script/style content is
    dropped. Image alt text is dropped (we don't want filename-derived names)."""

    SKIP_TAGS = {"script", "style", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1
        # Inject a newline at block-level elements so adjacent text doesn't run
        # together when we join.
        elif tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def extract_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


# ---------------------------------------------------------------- patterns

# All date / age / sex / status / municipio / address extraction lives in
# scripts/_text_extract_es.py — shared with every Spanish-text harvester.


# ---------------------------------------------------------------- harvester base

class PrpbAlertasBase(HarvestBase):
    """Subclass and set ``SOURCE_ID``, ``PLAN_MATCH``, ``INCIDENT_CLASS``,
    ``EXPECTED_SEX`` (optional — overrides sex when the plan implies it,
    e.g. ROSA → F). The base handles HTML iteration, parsing, normalization."""

    SOURCE_STRATUM = "A"
    PLAN_MATCH: str = ""
    INCIDENT_CLASS: str = ""
    EXPECTED_SEX: str = ""        # "F" for ROSA; otherwise "" (parse from text)

    # PRPB Alertas do not carry raw lat/lon on the alert page — coordinates
    # are always derived from the address text by the geocoder. The base sets
    # ``last_seen_geocode_method = "pending"`` so the consolidator (phase 2b)
    # knows to call the geocoder before the row hits the layer.
    HAS_DIRECT_COORDS = False

    # ----- snapshot iteration -----

    def harvest(self, snapshot_dir: Path) -> Tuple[Path, int, int]:
        """Override: iterate every ``*.html`` file in the snapshot dir."""
        html_paths = sorted(snapshot_dir.glob("*.html"))
        if not html_paths:
            raise FileNotFoundError(f"No *.html files in {snapshot_dir}")
        snapshot_date = snapshot_dir.name
        canonical: List[Dict[str, str]] = []
        dropped = 0
        for html_path in html_paths:
            raw = self._html_to_raw(html_path)
            row = self.normalize_row(raw, snapshot_date)
            if row is None:
                dropped += 1
                continue
            canonical.append(row)
        out_path = snapshot_dir / self.canonical_filename()
        self.write_canonical(canonical, out_path)
        return out_path, len(canonical), dropped

    def _html_to_raw(self, html_path: Path) -> Dict[str, str]:
        """Extract structured-but-still-raw fields from one alert page."""
        html = html_path.read_text(encoding="utf-8", errors="replace")
        text = extract_text(html)
        # Collapse runs of whitespace but keep newlines as record separators.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()

        return {
            "alert_filename": html_path.name,
            "report_date_raw": match_after_cue(text, FIELD_CUES["report_date"]),
            "last_seen_date_raw": match_after_cue(text, FIELD_CUES["last_seen_date"]),
            "address_raw": extract_address(text),
            "municipio_guess": extract_municipio(text),
            "age_raw": extract_age(text),
            "sex_raw": extract_sex(text),
            "status_raw": extract_status(text),
        }

    # ----- canonical normalize -----

    def normalize_row(self, raw: Dict[str, str], snapshot_date: str) -> Optional[Dict[str, str]]:
        if not raw.get("alert_filename"):
            return None
        canonical = empty_canonical(snapshot_date, self.SOURCE_ID)

        # Stable per-alert ID = hash of the filename stem (operator-controlled).
        stem = raw["alert_filename"].rsplit(".", 1)[0]
        canonical["case_id_hash"] = hash_id(stem)
        # Hash the URL-equivalent (alert filename is a stand-in for source URL).
        canonical["source_record_url_hash"] = hash_id(stem)

        canonical["report_date"] = extract_date(raw.get("report_date_raw", ""))
        canonical["last_seen_date"] = extract_date(raw.get("last_seen_date_raw", ""))
        canonical["status"] = raw.get("status_raw") or "active"

        age = raw.get("age_raw", "")
        canonical["age_band"] = bucket_age(age)
        canonical["age_exact_known"] = "true" if age else ""

        canonical["sex"] = self.EXPECTED_SEX or normalize_sex(raw.get("sex_raw", ""))
        canonical["ethnicity_band"] = bucket_ethnicity("")  # PRPB doesn't carry ethnicity

        # Coordinates come from the geocoder later (consolidator step) — we
        # carry the address forward in circumstances_subcategory so the
        # geocoder has its input on the row itself. Address is NOT PII (it's
        # an incident location, not a name).
        canonical["last_seen_lat"] = ""
        canonical["last_seen_lon"] = ""
        canonical["last_seen_geocode_method"] = "pending" if raw.get("address_raw") else ""
        canonical["last_seen_municipio"] = raw.get("municipio_guess", "")
        canonical["circumstances_subcategory"] = raw.get("address_raw", "")

        canonical["incident_class"] = validate_incident_class(self.INCIDENT_CLASS)
        canonical["plan_match"] = self.PLAN_MATCH

        return canonical
