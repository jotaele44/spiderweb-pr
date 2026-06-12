"""
Tests for the NamUs missing-persons ingestion pipeline.

Covers two surfaces:

1. ``scripts/namus_harvest`` — redaction contract: names, photos, DOB, and
   free-text narrative must not appear in the canonical CSV. case_id hashed.
   Status, age band, sex, and coordinates normalized.

2. ``scripts/populate_dataset_layers.emit_missing_persons_layers`` — both
   derived GIS layers (case-level points + aggregated municipio polygons) are
   emitted with correct CRS, _meta provenance, and bbox / coverage rules.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import namus_harvest  # noqa: E402


# The repo-wide conftest auto-seeds via pipeline.seeding, which was migrated to
# skywatcher-pr along with the flight subsystem. Override the autouse fixture
# locally so these tests don't depend on stripped modules. The missing-persons
# pipeline is fully deterministic without an RNG, so a no-op is correct.
@pytest.fixture(autouse=True)
def _deterministic_seed():
    yield

FIXTURE_CSV = REPO_ROOT / "tests" / "fixtures" / "namus_mp_pr_sample.csv"
MUNICIPIOS_GEOJSON = REPO_ROOT / "data" / "municipios.geojson"

# Fields that must never appear in any committed downstream artifact.
PII_FIELDS = {"First Name", "Last Name", "Date of Birth", "Circumstances of Disappearance", "Photo URL"}


# ---------------------------------------------------------------- harvest

@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    """A snapshot dir with the fixture CSV staged as if just downloaded."""
    snap = tmp_path / "2026-06-11"
    snap.mkdir()
    shutil.copy(FIXTURE_CSV, snap / "namus_mp_pr.csv")
    return snap


def test_harvest_emits_canonical_csv(snapshot: Path) -> None:
    out_path, kept, dropped = namus_harvest.harvest(snapshot)

    assert out_path == snapshot / "namus_mp_pr_canonical.csv"
    assert kept == 9, "9 rows have case numbers; 1 row has empty Case Number"
    assert dropped == 1


def test_harvest_redaction_drops_pii(snapshot: Path) -> None:
    out_path, _, _ = namus_harvest.harvest(snapshot)
    text = out_path.read_text(encoding="utf-8")

    # No first/last names from the fixture survive into canonical.
    for name in ["Maria", "Rivera", "Juan", "Santos", "Anibal", "Sofia", "Mendez",
                 "Luis", "Gomez", "Ana", "Torres", "Carlos", "Vargas", "Elena", "Daniel"]:
        assert name not in text, f"PII leak: '{name}' found in canonical CSV"

    # Narrative, DOB, photo URLs gone.
    assert "Last seen leaving" not in text
    assert "1995-04-12" not in text
    assert "namus.example/photos" not in text

    # Header has only the canonical columns.
    with out_path.open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == namus_harvest.CANONICAL_COLUMNS


def test_harvest_case_id_is_hashed_and_stable(snapshot: Path) -> None:
    out_path, _, _ = namus_harvest.harvest(snapshot)
    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))

    for r in rows:
        assert len(r["case_id_hash"]) == 12
        # No raw NamUs case numbers (MP##### form) survive.
        assert not r["case_id_hash"].startswith("MP")

    # Hash is deterministic.
    assert namus_harvest.hash_case_id("MP12345") == namus_harvest.hash_case_id("MP12345")
    assert namus_harvest.hash_case_id("MP12345") != namus_harvest.hash_case_id("MP12346")


def test_harvest_status_age_sex_normalization(snapshot: Path) -> None:
    out_path, _, _ = namus_harvest.harvest(snapshot)
    rows = {r["case_id_hash"]: r for r in csv.DictReader(out_path.open(encoding="utf-8"))}

    by_age = {r["age_band"] for r in rows.values()}
    # Ages: 28, 65, 9, 15, 38, 53, 21, 31, 43 → bands across the spectrum.
    assert {"0_12", "13_17", "18_30", "31_50", "51_plus"} <= by_age

    by_status = {r["status"] for r in rows.values()}
    assert {"active", "resolved_alive", "resolved_deceased", "cold"} <= by_status

    by_sex = {r["sex"] for r in rows.values()}
    assert by_sex == {"M", "F"}


def test_harvest_v2_extended_fields(snapshot: Path) -> None:
    """Phase 2a: every row carries source_id, incident_class, geocode method,
    ethnicity_band, and the empty-but-present linkage placeholders."""
    out_path, _, _ = namus_harvest.harvest(snapshot)
    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))

    # Schema: every v2 column is in the header and exists on every row.
    expected = set(namus_harvest.CANONICAL_COLUMNS)
    assert set(rows[0].keys()) == expected, "header drift from canonical contract"

    # source_id is uniformly tagged.
    assert {r["source_id"] for r in rows} == {"namus"}

    # incident_class is non-empty and drawn from the known enum for the
    # Missing-Persons stream.
    classes = {r["incident_class"] for r in rows}
    assert classes <= {"missing_juvenile", "missing_adult_woman", "missing_adult_other"}, classes
    # Fixture has 1 child (9), 1 teen (15), so both juvenile rows present.
    assert "missing_juvenile" in classes
    assert "missing_adult_woman" in classes

    # Direct-coord rows carry the geocode method tag.
    direct_rows = [r for r in rows if r["last_seen_lat"]]
    assert direct_rows, "fixture should have direct-coord rows"
    assert all(r["last_seen_geocode_method"] == "direct" for r in direct_rows)

    # age_exact_known is "true" when raw age was present (always in fixture).
    assert all(r["age_exact_known"] == "true" for r in rows)

    # Consolidator placeholders exist but are empty at harvest.
    for r in rows:
        assert r["linkage_keys_json"] == ""
        assert r["coord_disagreement_km"] == ""
        assert r["last_seen_municipio"] == ""  # populated by populate step, not harvest


def test_harvest_preserves_coordinates(snapshot: Path) -> None:
    out_path, _, _ = namus_harvest.harvest(snapshot)
    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))

    lats = {float(r["last_seen_lat"]) for r in rows if r["last_seen_lat"]}
    # Miami-Dade out-of-PR row (25.76, -80.19) is still in canonical — harvest
    # does not bbox-filter; that is the populate step's job.
    assert 25.7617 in lats
    # PR coordinates also present.
    assert 18.4222 in lats


# ---------------------------------------------------------------- populate

@pytest.fixture
def populate_module():
    # Imported lazily so harvest-only tests stay light if the populate
    # extension has not landed yet during in-progress edits.
    from scripts import populate_dataset_layers
    return populate_dataset_layers


@pytest.fixture
def emitted(tmp_path: Path, snapshot: Path, populate_module):
    """Run the missing-persons emission against the fixture and return the
    written FeatureCollections."""
    out_dir = tmp_path / "gis_layers"
    out_dir.mkdir()
    manifest = tmp_path / "gis_layers_manifest.json"

    # Harvest first so canonical exists.
    canonical, _, _ = namus_harvest.harvest(snapshot)

    lw = populate_module.LayerWriter(out_dir=out_dir, manifest_path=manifest)
    populate_module.emit_missing_persons_layers(
        lw, canonical_csv=canonical, municipios_geojson=MUNICIPIOS_GEOJSON,
    )
    lw.flush()

    cases_fc = json.loads((out_dir / "missing_persons_cases.geojson").read_text())
    muni_fc = json.loads((out_dir / "missing_persons_by_municipio.geojson").read_text())
    return cases_fc, muni_fc


def test_cases_layer_filters_out_of_pr(emitted) -> None:
    cases_fc, _ = emitted
    # 9 canonical rows after harvest; 1 is out-of-PR (Miami-Dade) → 8 features.
    assert len(cases_fc["features"]) == 8
    assert cases_fc["meta"]["skipped_no_coords"] >= 1  # the out-of-PR row counted as skipped
    assert cases_fc["meta"]["domain"] == "public_safety"
    assert cases_fc["meta"]["role"] == "primary"
    assert cases_fc["meta"]["crs"] == "EPSG:4326"


def test_cases_features_carry_meta_and_no_pii(emitted) -> None:
    cases_fc, _ = emitted
    text = json.dumps(cases_fc)

    for name in ["Maria", "Rivera", "Juan", "Santos", "Sofia", "Mendez"]:
        assert name not in text, f"PII leak in cases layer: {name}"
    assert "namus.example/photos" not in text

    for feat in cases_fc["features"]:
        assert feat["geometry"]["type"] == "Point"
        lon, lat = feat["geometry"]["coordinates"]
        assert -68.0 <= lon <= -65.1
        assert 17.6 <= lat <= 18.7
        assert "_meta" in feat["properties"]
        assert "case_id_hash" in feat["properties"]


def test_municipio_aggregate_preserves_zero_counts(emitted) -> None:
    _, muni_fc = emitted
    # Every municipio must appear, even with zero cases.
    expected_count = len(json.loads(MUNICIPIOS_GEOJSON.read_text())["features"])
    assert len(muni_fc["features"]) == expected_count
    assert muni_fc["meta"]["domain"] == "public_safety"
    assert muni_fc["meta"]["role"] == "aggregate"

    case_counts = {f["properties"]["NAME"]: f["properties"]["case_count"]
                   for f in muni_fc["features"]}
    # Fixture has 3 cases in San Juan, 2 in Caguas — verify nonzero municipios exist.
    assert case_counts.get("San Juan", 0) >= 3
    assert case_counts.get("Caguas", 0) >= 2
    # And at least one municipio with zero cases is preserved.
    assert any(v == 0 for v in case_counts.values())


def test_municipio_aggregate_status_breakdown(emitted) -> None:
    _, muni_fc = emitted
    total_active = sum(f["properties"].get("case_count_active", 0) for f in muni_fc["features"])
    total_resolved = sum(f["properties"].get("case_count_resolved", 0) for f in muni_fc["features"])
    # Fixture (PR-only): active = MP12345, MP12347, MP12348(cold→not active), MP12350, MP12351
    # Cold cases are not "active". Active in PR fixture: MP12345, MP12347, MP12350, MP12351 = 4
    # Resolved (alive or deceased) in PR: MP12346, MP12349, MP12352 = 3
    assert total_active == 4
    assert total_resolved == 3
