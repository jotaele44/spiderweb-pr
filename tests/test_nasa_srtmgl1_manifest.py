"""SRTMGL1 source manifest: schema, tiles from CMR, repo policy, observed composition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "data_sources" / "nasa" / "srtmgl1.yml"
SCHEMA = REPO_ROOT / "schemas" / "raster_source_manifest.schema.json"
RECEIPT = REPO_ROOT / "evidence" / "dem_sources" / "srtmgl1_pr_2026-11-23"
PR_TILES = ["N17W066", "N17W067", "N17W068", "N18W066", "N18W067", "N18W068"]
ARCSEC = 1 / 3600


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_validates_against_raster_schema(manifest: dict) -> None:
    jsonschema.validate(manifest, json.loads(SCHEMA.read_text()))
    assert manifest["source_family"] == "NASA_LPDAAC_SRTMGL1"
    assert manifest["collection"]["concept_id"] == "C2763266360-LPCLOUD"
    assert manifest["collection"]["num_companion"]["concept_id"] == "C2763266368-LPCLOUD"


def test_six_pr_tiles_with_lpdaac_urls(manifest: dict) -> None:
    tiles = manifest["datasets"][0]["tiles"]
    assert [t["tile_id"] for t in tiles] == PR_TILES
    for t in tiles:
        tid = t["tile_id"]
        assert t["https_url"] == f"https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/{tid}.SRTMGL1.hgt/{tid}.SRTMGL1.hgt.zip"
        assert t["num"]["https_url"] == f"https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1N.003/{tid}.SRTMGL1N.num/{tid}.SRTMGL1N.num.zip"
        assert t["snapshot_footprint_matches_cmr"] is True


def test_cmr_footprint_is_padded_one_arcsecond_and_grid_extent_half(manifest: dict) -> None:
    for t in manifest["datasets"][0]["tiles"]:
        lat = int(t["tile_id"][1:3])
        lon = -int(t["tile_id"][4:7])
        w, s, e, n = t["cmr_footprint_wsen"]
        assert w == pytest.approx(lon - ARCSEC, abs=1e-8) and e == pytest.approx(lon + 1 + ARCSEC, abs=1e-8)
        assert s == pytest.approx(lat - ARCSEC, abs=1e-8) and n == pytest.approx(lat + 1 + ARCSEC, abs=1e-8)
        gw, gs, ge, gn = t["grid_extent_wsen"]
        assert gw == pytest.approx(lon - ARCSEC / 2, abs=1e-9) and gn == pytest.approx(lat + 1 + ARCSEC / 2, abs=1e-9)


def test_raw_tiles_are_never_committed(manifest: dict) -> None:
    for pattern in ("*.hgt", "*.hgt.zip", "*.num", "*.num.zip"):
        assert pattern in manifest["repo_policy"]["do_not_commit"]
    snapshot = manifest["source_snapshots"][0]
    assert snapshot["feature_count"] == 14295 and len(snapshot["sha256"]) == 64
    assert manifest["catalog_coverage"]["missing_from_snapshot"] == ["S29W055", "S56W072"]


def test_observed_composition_matches_the_receipt(manifest: dict) -> None:
    observed = manifest["datasets"][0]["observed_composition"]
    receipt = json.loads((RECEIPT / "composition.json").read_text())
    assert observed["land_samples"] == sum(t["land_samples"] for t in receipt["tiles"])
    for category, count in observed["land_category_counts"].items():
        assert count == sum(t["category_counts"][category] for t in receipt["tiles"]), category
    assert observed["land_share_percent"]["srtm_measured"] > 99.9
    gaps = {g["gap_id"]: g for g in manifest["gaps"]}
    assert gaps["SRTMGL1_GAP_001"]["status"].startswith("closed_")
    assert "status" not in gaps["SRTMGL1_GAP_002"]


def test_receipt_holds_no_credentials() -> None:
    text = (RECEIPT / "provenance.json").read_text()
    for marker in ("Bearer", "Authorization", "Signature", "X-Amz", "Key-Pair-Id", "cloudfront.net/"):
        assert marker not in text
    files = json.loads(text)["files"]
    assert len(files) == 12 and all(f["raw_commit_allowed"] is False for f in files)
