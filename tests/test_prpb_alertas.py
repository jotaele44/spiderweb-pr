"""
Tests for the 4 PRPB Alertas harvesters (phase 2c.1).

Covers:
  * HTML → text extraction (script tags dropped, structure flattened)
  * Date format normalization (ISO, slash, Spanish long form)
  * Age / sex / municipio / status extraction
  * Plan-coded class assignment (AMBER → missing_juvenile, ROSA → endangered_woman, …)
  * Sex override (ROSA forces F regardless of page content)
  * PII boundary (names NEVER appear in canonical output)
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.prpb_alertas_amber_harvest import PrpbAlertasAmberHarvest  # noqa: E402
from scripts.prpb_alertas_ashanti_harvest import PrpbAlertasAshantiHarvest  # noqa: E402
from scripts.prpb_alertas_rosa_harvest import PrpbAlertasRosaHarvest  # noqa: E402
from scripts.prpb_alertas_silver_harvest import PrpbAlertasSilverHarvest  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "prpb_alertas"

# Names visible in fixture HTML — these must NEVER leak into the canonical CSV.
PII_NAMES = ["Anibal", "Cruz", "Mercado", "Maria", "Rivera", "Sanchez",
             "Juan", "Santos", "Mendez", "Carlos", "Vargas", "Pereira"]


@pytest.fixture(autouse=True)
def _deterministic_seed():
    # Same conftest override as test_missing_persons_layer.py: pipeline.seeding
    # was migrated out of the repo, so the autouse fixture would crash setup.
    yield


def _stage(tmp_path: Path, fixture: str) -> Path:
    """Drop one fixture HTML into a fresh snapshot dir under tmp_path."""
    snap = tmp_path / "2026-06-12"
    snap.mkdir()
    shutil.copy(FIXTURES / fixture, snap / fixture)
    return snap


def _run(harvester, snap):
    out_path, kept, dropped = harvester.harvest(snap)
    return out_path, kept, dropped, list(csv.DictReader(out_path.open(encoding="utf-8")))


# ---------------------------------------------------------------- AMBER

def test_amber_extracts_minor_with_iso_date(tmp_path):
    snap = _stage(tmp_path, "ALERT-AMBER-2024-007.html")
    out_path, kept, dropped, rows = _run(PrpbAlertasAmberHarvest(), snap)
    assert kept == 1 and dropped == 0
    row = rows[0]
    assert row["plan_match"] == "AMBER"
    assert row["incident_class"] == "missing_juvenile"
    assert row["report_date"] == "2024-01-10"
    assert row["last_seen_date"] == "2024-01-09"
    assert row["age_band"] == "0_12"             # 9 years old
    assert row["sex"] == "M"
    assert row["last_seen_municipio"] == "Carolina"
    assert row["status"] == "active"
    assert row["last_seen_geocode_method"] == "pending"
    # Address survives as circumstances_subcategory for the geocoder later.
    assert "Carolina" in row["circumstances_subcategory"]


# ---------------------------------------------------------------- ROSA

def test_rosa_overrides_sex_and_extracts_spanish_long_form_date(tmp_path):
    snap = _stage(tmp_path, "ALERT-ROSA-2024-012.html")
    _out, _kept, _dropped, rows = _run(PrpbAlertasRosaHarvest(), snap)
    row = rows[0]
    assert row["plan_match"] == "ROSA"
    assert row["incident_class"] == "endangered_woman"
    assert row["report_date"] == "2024-03-15"
    assert row["sex"] == "F"                     # plan override
    assert row["age_band"] == "18_30"
    assert row["last_seen_municipio"] == "Caguas"


# ---------------------------------------------------------------- SILVER

def test_silver_handles_slash_dates_and_resolved_status(tmp_path):
    snap = _stage(tmp_path, "ALERT-SILVER-2024-031.html")
    _out, _kept, _dropped, rows = _run(PrpbAlertasSilverHarvest(), snap)
    row = rows[0]
    assert row["plan_match"] == "SILVER"
    assert row["incident_class"] == "cognitive_impairment"
    # Slash format is DD/MM/YYYY in PR convention; normalized to ISO.
    assert row["report_date"] == "2024-03-12"
    assert row["last_seen_date"] == "2024-03-11"
    assert row["age_band"] == "51_plus"
    assert row["status"] == "resolved_alive"     # "RESUELTO" → resolved_alive
    assert row["last_seen_municipio"] == "Ponce"


# ---------------------------------------------------------------- ASHANTI

def test_ashanti_extracts_emitido_date_cue(tmp_path):
    snap = _stage(tmp_path, "ALERT-ASHANTI-2024-045.html")
    _out, _kept, _dropped, rows = _run(PrpbAlertasAshantiHarvest(), snap)
    row = rows[0]
    assert row["plan_match"] == "ASHANTI"
    assert row["incident_class"] == "endangered_adult"
    assert row["report_date"] == "2024-02-14"
    assert row["last_seen_date"] == "2024-02-12"
    assert row["age_band"] == "18_30"
    assert row["sex"] == "M"
    assert row["last_seen_municipio"] == "Bayamón"


# ---------------------------------------------------------------- redaction boundary

def test_no_names_or_photo_urls_leak_for_any_plan(tmp_path):
    """The hardest property to break: across ALL 4 plans, NO name string from
    any fixture leaks into the canonical CSV. This pins the PII boundary."""
    cases = [
        (PrpbAlertasAmberHarvest(), "ALERT-AMBER-2024-007.html"),
        (PrpbAlertasRosaHarvest(), "ALERT-ROSA-2024-012.html"),
        (PrpbAlertasSilverHarvest(), "ALERT-SILVER-2024-031.html"),
        (PrpbAlertasAshantiHarvest(), "ALERT-ASHANTI-2024-045.html"),
    ]
    for i, (harvester, fixture) in enumerate(cases):
        sub = tmp_path / f"case_{i}"
        sub.mkdir()
        snap = _stage(sub, fixture)
        out_path, _kept, _dropped, _rows = _run(harvester, snap)
        text = out_path.read_text(encoding="utf-8")
        for name in PII_NAMES:
            assert name not in text, f"PII leak for {fixture}: {name!r} in {out_path.name}"
        # Photo URLs and image filenames must not leak either.
        assert "photos" not in text.lower()
        assert ".jpg" not in text.lower()


def test_case_id_hashed_per_filename(tmp_path):
    snap = _stage(tmp_path, "ALERT-AMBER-2024-007.html")
    _out, _kept, _dropped, rows = _run(PrpbAlertasAmberHarvest(), snap)
    row = rows[0]
    assert len(row["case_id_hash"]) == 12
    assert not row["case_id_hash"].startswith("ALERT")  # not the raw stem


def test_v2_schema_intact_for_alertas_harvesters(tmp_path):
    """Header equality with the v2 canonical contract."""
    from scripts._harvest_base import CANONICAL_COLUMNS
    snap = _stage(tmp_path, "ALERT-ROSA-2024-012.html")
    out_path, _, _, rows = _run(PrpbAlertasRosaHarvest(), snap)
    assert set(rows[0].keys()) == set(CANONICAL_COLUMNS)
    # source_id is uniformly tagged per harvester subclass.
    assert rows[0]["source_id"] == "prpb_alertas_rosa"
