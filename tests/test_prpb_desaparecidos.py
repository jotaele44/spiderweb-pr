"""
Tests for the PRPB Desaparecidos gallery harvester (phase 2c.2).

Multi-card extraction is the hard part. The fixture is one HTML page with 6
person cards; the harvester must emit exactly 6 canonical rows, none of them
containing the visible victim names.
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts._harvest_base import CANONICAL_COLUMNS  # noqa: E402
from scripts.prpb_desaparecidos_harvest import PrpbDesaparecidosHarvest  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "prpb_desaparecidos" / "gallery_p1.html"

# Victim names from the fixture that must NEVER reach the canonical CSV.
# We check FULL surnames and uncommon first names — bare 'Juan' (which would
# false-positive on the 'San Juan' municipio) and bare 'Ana' (matches the
# letter combination in other words) are NOT in this list. The complete
# victim names are still verified via the multi-token check below.
PII_NAMES = ["Rivera", "Sanchez", "Anibal", "Mercado",
             "Santos", "Mendez", "Carlos", "Vargas", "Pereira",
             "Torres", "Pinero", "Daniel", "Soto", "Perez"]
PII_FULL_NAMES = ["Maria Rivera", "Anibal Cruz", "Juan Santos",
                  "Carlos Vargas", "Ana Torres", "Daniel Soto"]


@pytest.fixture(autouse=True)
def _deterministic_seed():
    yield


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    snap = tmp_path / "2026-06-12"
    snap.mkdir()
    shutil.copy(FIXTURE, snap / "page_1.html")
    return snap


def _run(snap: Path):
    out_path, kept, dropped = PrpbDesaparecidosHarvest().harvest(snap)
    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))
    return out_path, kept, dropped, rows


def test_extracts_six_cards_from_gallery(snapshot: Path) -> None:
    _out, kept, dropped, rows = _run(snapshot)
    assert kept == 6, f"expected 6 cards extracted, got {kept}"
    assert dropped == 0
    assert len(rows) == 6


def test_every_row_carries_v2_schema(snapshot: Path) -> None:
    _out, _kept, _dropped, rows = _run(snapshot)
    for r in rows:
        assert set(r.keys()) == set(CANONICAL_COLUMNS)
        assert r["source_id"] == "prpb_desaparecidos"


def test_juvenile_age_flips_incident_class(snapshot: Path) -> None:
    _out, _kept, _dropped, rows = _run(snapshot)
    classes = {r["age_band"]: r["incident_class"] for r in rows}
    # 9-year-old and 14-year-old in the fixture → both flip to missing_juvenile.
    assert classes.get("0_12") == "missing_juvenile"
    assert classes.get("13_17") == "missing_juvenile"
    # Adults default to missing_adult_other. (No 31_50 case in fixture; the
    # 28/21/53 cases land in 18_30 and 51_plus respectively.)
    assert classes.get("18_30") == "missing_adult_other"
    assert classes.get("51_plus") == "missing_adult_other"


def test_municipio_resolved_per_card(snapshot: Path) -> None:
    _out, _kept, _dropped, rows = _run(snapshot)
    municipios = {r["last_seen_municipio"] for r in rows}
    # Every fixture card mentions a municipio; the matcher should resolve each.
    assert {"San Juan", "Carolina", "Ponce", "Bayamón", "Mayagüez", "Caguas"} <= municipios


def test_no_victim_names_leak_to_canonical(snapshot: Path) -> None:
    out_path, _kept, _dropped, _rows = _run(snapshot)
    text = out_path.read_text(encoding="utf-8")
    for name in PII_NAMES:
        assert name not in text, f"PII leak: {name!r} in canonical"
    # The full victim names ('Maria Rivera', 'Juan Santos', etc.) must not
    # appear together — this catches any case where 'Juan' from the municipio
    # might collide with 'Juan' from the victim. They never run together.
    for full in PII_FULL_NAMES:
        assert full not in text, f"PII leak: {full!r} in canonical"
    # Photo URLs should also not survive — only their hashed stem.
    assert ".jpg" not in text.lower()
    assert "photos" not in text.lower()


def test_case_id_hash_is_stable_per_photo(snapshot: Path) -> None:
    """Re-running the harvester on the same snapshot produces identical
    case_id_hash values. The hash is derived from the photo filename stem,
    so re-pulls of the same PRPB row land on the same id."""
    _out1, _, _, rows1 = _run(snapshot)
    _out2, _, _, rows2 = _run(snapshot)
    hashes1 = sorted(r["case_id_hash"] for r in rows1)
    hashes2 = sorted(r["case_id_hash"] for r in rows2)
    assert hashes1 == hashes2
    # All 6 hashes must be distinct — no cross-card collisions.
    assert len(set(hashes1)) == 6


def test_date_extraction_when_present(snapshot: Path) -> None:
    _out, _kept, _dropped, rows = _run(snapshot)
    # Two of the six fixture cards mention an ISO date in the caption.
    rows_with_date = [r for r in rows if r["last_seen_date"]]
    assert len(rows_with_date) >= 1


def test_geocode_method_pending_for_municipio_matched_rows(snapshot: Path) -> None:
    _out, _kept, _dropped, rows = _run(snapshot)
    # Every fixture card resolved a municipio, so every row should be
    # geocode_method=pending (consolidator will geocode the municipio centroid
    # or, with a real address, a more precise point).
    assert all(r["last_seen_geocode_method"] == "pending" for r in rows)


# ---------------------------------------------------------------- review fixes
# These pin the 2026-06-12 adversarial-review HIGH findings against realistic
# PRPB markup: thumbnail-WRAPPER divs around the photo, a page logo, and
# per-card share icons. The original parser dropped captions on wrapper divs
# and turned every logo/icon <img> into a phantom row.

WRAPPED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "prpb_desaparecidos" / "gallery_wrapped.html"


@pytest.fixture
def wrapped_snapshot(tmp_path: Path) -> Path:
    snap = tmp_path / "2026-06-12"
    snap.mkdir()
    shutil.copy(WRAPPED_FIXTURE, snap / "page_1.html")
    return snap


def test_wrapper_div_does_not_drop_caption(wrapped_snapshot: Path) -> None:
    """The HIGH bug: a <div class=thumb> wrapper around the <img> used to fire
    a premature card-close, dropping municipio/age. Now the caption survives."""
    _out, kept, dropped, rows = _run(wrapped_snapshot)
    # Exactly 2 person cards — NOT the logo, NOT the share/phone icons.
    assert kept == 2, f"expected 2 person cards, got {kept}"
    by_muni = {r["last_seen_municipio"]: r for r in rows}
    assert "San Juan" in by_muni, "caption (municipio) was dropped on wrapper div"
    assert "Carolina" in by_muni
    # The 9-year-old's caption survived, so the juvenile flip fires.
    assert by_muni["Carolina"]["incident_class"] == "missing_juvenile"
    assert by_muni["Carolina"]["age_band"] == "0_12"
    assert by_muni["San Juan"]["age_band"] == "18_30"


def test_logo_and_share_icons_never_become_rows(wrapped_snapshot: Path) -> None:
    """The HIGH bug: page logo + per-card share icons used to emit phantom
    rows, and reused icon srcs collided case_id_hash."""
    out_path, _kept, _dropped, rows = _run(wrapped_snapshot)
    text = out_path.read_text(encoding="utf-8")
    # No logo/icon artifacts in any row.
    for junk in ["logo", "share", "icon-phone", ".svg", ".png"]:
        assert junk not in text.lower(), f"phantom artifact {junk!r} leaked into canonical"
    # case_id_hash must be the person-photo stem, distinct per person.
    hashes = [r["case_id_hash"] for r in rows]
    assert len(set(hashes)) == 2, "icon src collision produced duplicate case_id_hash"


def test_wrapped_photo_src_is_person_not_icon(wrapped_snapshot: Path) -> None:
    """case_id derives from the PERSON photo, not the trailing share icon."""
    _out, _kept, _dropped, rows = _run(wrapped_snapshot)
    # source_record_url_hash is derived from the photo src; the two person
    # photos differ, so the two hashes differ. (We can't read the raw src from
    # the canonical — it's hashed — but a collision would have shown identical
    # source_record_url_hash values for the two distinct people.)
    url_hashes = {r["source_record_url_hash"] for r in rows}
    assert len(url_hashes) == 2
