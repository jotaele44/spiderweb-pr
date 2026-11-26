"""Pilot qualification fixtures for FED-GEO-SAR-001 (deliverable D17).

Everything here runs offline against bytes kept from the one authorised
metadata discovery run.  The cases are taken from what the provider actually
publishes for the pilot extent, not invented: two files with unrelated names
that cover the same ground, files with near-identical names that do not, and
one survey published in several lots per tile position.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "registry" / "geo_sar"
EVIDENCE = REPO_ROOT / "evidence" / "geo_sar" / "pilot_001" / "discovery"
SCHEMAS = REPO_ROOT / "schemas"

from scripts import geo_sar_pilot_discovery as discovery  # noqa: E402


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger():
    return _load(REGISTRY / "pilot_001_asset_ledger.json")


@pytest.fixture(scope="module")
def receipt():
    return _load(EVIDENCE / "discovery_receipt.json")


def _asset(ledger, tile_id: str):
    (found,) = [a for a in ledger["assets"] if a["asset_id"] == f"USGS3DEP:{tile_id}"]
    return found


def _overlap_fraction(a, b) -> float:
    """Shared area over the first footprint's area, computed in the grid CRS.

    Exact reprojected footprints are used on purpose: latitude/longitude
    bounding boxes of these rotated tiles overstate how much they share.
    """

    pytest.importorskip("rasterio")
    pytest.importorskip("shapely")
    first, second = (
        discovery._to_grid(
            x["verified"]["native_footprint"], x["verified"]["native_crs"]
        )
        for x in (a, b)
    )
    return first.intersection(second).area / first.area


# -- registries are well formed and point at code that exists --------------


@pytest.mark.parametrize(
    ("registry", "schema"),
    [
        ("pilot_001_asset_ledger", "geo_sar_asset_ledger"),
        ("comparison_methods", "geo_sar_comparison_methods"),
        ("gap_taxonomy", "geo_sar_gap_taxonomy"),
        ("pilot_001_gaps", "geo_sar_gap_registry"),
    ],
)
def test_registry_matches_its_schema(registry, schema):
    document = _load(SCHEMAS / f"{schema}.schema.json")
    jsonschema.Draft202012Validator.check_schema(document)
    jsonschema.Draft202012Validator(document).validate(
        _load(REGISTRY / f"{registry}.json")
    )


def test_every_registered_method_exists_in_code():
    registry = _load(REGISTRY / "comparison_methods.json")
    taxonomy = _load(REGISTRY / "gap_taxonomy.json")
    references = [m["implementation"] for m in registry["methods"]]
    references += registry["existing_eligibility_code"]
    references += taxonomy["existing_state_vocabularies"]
    assert references
    for reference in references:
        source = (REPO_ROOT / reference["path"]).read_text(encoding="utf-8")
        pattern = rf"^(def|class)\s+{re.escape(reference['symbol'])}\b"
        assert re.search(pattern, source, re.MULTILINE), reference
    # Listing a method does not qualify it.
    assert {m["qualification_state"] for m in registry["methods"]} == {"UNVERIFIED"}


def test_pilot_gaps_use_the_taxonomy_and_cite_existing_evidence():
    codes = {c["code"] for c in _load(REGISTRY / "gap_taxonomy.json")["classes"]}
    assert codes == {f"G{n:02d}" for n in range(1, 17)}
    gaps = _load(REGISTRY / "pilot_001_gaps.json")["gaps"]
    assert len({g["gap_id"] for g in gaps}) == len(gaps)
    for gap in gaps:
        assert gap["class"] in codes
        for path in gap["supporting_evidence"]:
            assert (REPO_ROOT / path).is_file(), path


# -- discovery controls -----------------------------------------------------


def test_nothing_is_granted_by_default(tmp_path):
    for raw in ("", "150", "0:owner", "150:", "many:owner", "-1:owner"):
        with pytest.raises(discovery.DiscoveryRefused):
            discovery.parse_grant(raw)
    assert discovery.parse_grant("150:owner") == (150, "owner")
    code = discovery.main(
        ["run", "--evidence", str(tmp_path / "e"), "--ledger", str(tmp_path / "l.json")]
    )
    assert code == 2 and not (tmp_path / "e").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://tnmaccess.nationalmap.gov/api/v1/products",
        "https://example.org/api/v1/products",
        "https://tnmaccess.nationalmap.gov.example.org/x",
        "https://user:secret@prd-tnm.s3.amazonaws.com/x.tif",
        "https://prd-tnm.s3.amazonaws.com:8443/x.tif",
        "https://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
    ],
)
def test_urls_outside_the_allow_list_are_refused(url):
    with pytest.raises(discovery.DiscoveryRefused):
        discovery.check_url(url)


def test_request_budget_is_enforced_before_the_network_is_touched(monkeypatch):
    opened = []
    monkeypatch.setattr(
        discovery, "build_opener", lambda *a: opened.append(a) or _NeverOpens()
    )
    fetch, used = discovery.live_fetch(max_requests=1)
    used[0] = 1
    with pytest.raises(discovery.DiscoveryRefused, match="budget"):
        fetch(discovery.TNM_PRODUCTS_URL, None)
    assert used[0] == 1


class _NeverOpens:
    def open(self, *args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("the network was touched")


def test_receipt_stays_inside_the_grant(receipt):
    assert receipt["authorization"]["level"] == "METADATA_DISCOVERY"
    assert receipt["requests_made"] == len(receipt["requests"])
    assert receipt["requests_made"] <= receipt["authorization"]["max_requests"] <= 150
    assert set(receipt["hosts_contacted"]) <= set(discovery.ALLOWED_HOSTS)
    assert receipt["data_products_downloaded"] == 0
    for request in receipt["requests"]:
        if request["purpose"] != "catalog":
            assert request["status"] == 206
            assert request["byte_range"] == f"0-{discovery.HEADER_BYTES - 1}"
            assert request["response_size"] <= discovery.HEADER_BYTES
        assert (EVIDENCE / request["body_file"]).is_file()


# -- replay -----------------------------------------------------------------


def test_replay_reproduces_the_committed_ledger(ledger):
    pytest.importorskip("rasterio")
    pytest.importorskip("shapely")
    rebuilt, log = discovery.discover(discovery.replay_fetch(EVIDENCE))
    assert rebuilt == ledger
    assert len(log) == 29


def test_replay_refuses_changed_bytes(tmp_path):
    copy = tmp_path / "discovery"
    shutil.copytree(EVIDENCE, copy)
    target = copy / "req_0003.bin"
    damaged = bytearray(target.read_bytes())
    damaged[100] ^= 0xFF
    target.write_bytes(bytes(damaged))
    with pytest.raises(discovery.DiscoveryRefused, match="changed"):
        discovery.replay_fetch(copy)


def test_a_finished_run_is_never_overwritten(tmp_path):
    code = discovery.main(
        [
            "run",
            "--grant",
            "150:owner",
            "--evidence",
            str(EVIDENCE),
            "--ledger",
            str(tmp_path / "ledger.json"),
        ]
    )
    assert code == 2 and not (tmp_path / "ledger.json").exists()


# -- ledger facts -----------------------------------------------------------


def test_catalogue_denominator_is_closed_and_every_footprint_is_from_the_file(ledger):
    assert ledger["catalog"]["denominator_state"] == "CLOSED"
    assert ledger["catalog"]["reported_total"] == len(ledger["assets"]) == 28
    assert ledger["registered_before_but_not_listed_now"] == []
    for asset in ledger["assets"]:
        verified = asset["verified"]
        assert verified["verification_status"] == "HEADER_VERIFIED"
        assert verified["object_size_bytes"] == asset["source_provided"]["size_bytes"]
        assert (
            asset["native_identity"]["catalog_snapshot_sha256"]
            == (ledger["catalog"]["snapshot_sha256"])
        )


def test_no_acquisition_or_integrity_result_is_claimed(ledger):
    for asset in ledger["assets"]:
        assert asset["availability"]["acquisition_status"] == "NOT_ACQUIRED"
        assert asset["integrity"]["computed_sha256"] is None
        assert asset["integrity"]["verification_status"] == "NOT_ACQUIRED"
        assert asset["storage"] == {"artifact_id": None, "local_path": None}
        assert asset["verified"]["vertical_datum"]["state"] == "CONTESTED"
        assert asset["verified"]["valid_data_extent"] == "UNVERIFIED"


def test_two_dataset_versions_cover_every_pilot_segment(ledger):
    versions = {v["dataset_version_id"] for v in ledger["dataset_versions"]}
    assert versions == {
        "USGS_3DEP_1M_PR_PRVI_2018@2018",
        "USGS_3DEP_1M_PR_PuertoRicoUSVI_D24@D24",
    }
    assert ledger["segmentation"]["segment_count"] == len(ledger["segments"]) == 42
    for segment in ledger["segments"]:
        assert set(segment["dataset_versions"]) == versions
        for coverage in segment["dataset_versions"].values():
            assert coverage["footprint_coverage_fraction"] == 1.0
            assert coverage["intersecting_assets"]


# -- fixtures for "footprints, not filenames" (principle 4) ----------------


def test_unrelated_filenames_can_be_the_same_ground(ledger):
    """Zone 19 tile x81y203 lies mostly under zone 20 tile x18y203."""

    a = _asset(ledger, "USGS_1M_19_x81y203_PR_PuertoRicoUSVI_D24")
    b = _asset(ledger, "USGS_1M_20_x18y203_PR_PuertoRicoUSVI_D24")
    assert a["verified"]["native_crs"] != b["verified"]["native_crs"]
    assert _overlap_fraction(a, b) > 0.5


def test_near_identical_filenames_can_be_different_ground(ledger):
    """x81y203 and x81y204 differ by one character and share only an edge strip."""

    a = _asset(ledger, "USGS_1M_19_x81y203_PR_PuertoRicoUSVI_D24")
    b = _asset(ledger, "USGS_1M_19_x81y204_PR_PuertoRicoUSVI_D24")
    assert 0 < _overlap_fraction(a, b) < 0.01


def test_the_same_tile_position_matches_across_versions(ledger):
    """2018 lot D and the 2024 file at x81y203 have the same footprint."""

    new = _asset(ledger, "USGS_1M_19_x81y203_PR_PuertoRicoUSVI_D24")
    old = _asset(ledger, "USGS_1m_x81y203_PR_PRVI_D_2018")
    assert _overlap_fraction(old, new) == pytest.approx(1.0, abs=1e-6)


def test_no_zone_20_file_substitutes_for_a_zone_19_file(ledger):
    """Known discrepancy fixture: 'alternate' does not hold file to file.

    The existing registry classes each zone 20N file ALTERNATE_COMPLETE.  The
    two tilings are offset, so every zone 19N file is split across zone 20N
    files.  Recorded as GEOSAR-PILOT-001-GAP-006.
    """

    d24 = [a for a in ledger["assets"] if a["dataset_version_id"].endswith("@D24")]
    zone19 = [a for a in d24 if a["verified"]["native_crs"] == "EPSG:26919"]
    zone20 = [a for a in d24 if a["verified"]["native_crs"] == "EPSG:26920"]
    assert len(zone19) == len(zone20) == 4
    for tile in zone19:
        best = max(_overlap_fraction(tile, other) for other in zone20)
        assert 0.35 < best < 0.65
    gaps = _load(REGISTRY / "pilot_001_gaps.json")["gaps"]
    assert any(g["gap_id"] == "GEOSAR-PILOT-001-GAP-006" for g in gaps)


def test_one_tile_position_can_hold_several_distinct_files(ledger):
    """The 2018 survey has lots D and H at x81y203: same extent, other bytes."""

    d = _asset(ledger, "USGS_1m_x81y203_PR_PRVI_D_2018")
    h = _asset(ledger, "USGS_1m_x81y203_PR_PRVI_H_2018")
    assert d["verified"]["native_footprint"] == h["verified"]["native_footprint"]
    assert d["source_provided"]["size_bytes"] != h["source_provided"]["size_bytes"]
    assert d["verified"]["header_sha256"] != h["verified"]["header_sha256"]
    assert d["asset_id"] != h["asset_id"]


def test_shared_assets_are_counted_once_across_segments(ledger):
    """42 segments need 28 files, not one copy per segment that touches them."""

    pairs = [
        (segment["segment_id"], item["asset_id"])
        for segment in ledger["segments"]
        for coverage in segment["dataset_versions"].values()
        for item in coverage["intersecting_assets"]
    ]
    unique = {asset_id for _, asset_id in pairs}
    assert unique == {a["asset_id"] for a in ledger["assets"]}
    assert len(pairs) > 5 * len(unique)


# -- evidence other lanes already hold --------------------------------------


def test_prior_acquisition_receipts_are_reconciled_not_adopted(ledger):
    """An earlier run in the elevation lane fetched three of these files.

    Its hashes are carried as prior evidence.  They are not promoted to this
    ledger's own integrity result, because the bytes are not held here.
    """

    prior = {
        a["asset_id"]: a["prior_acquisition"]
        for a in ledger["assets"]
        if a["prior_acquisition"]
    }
    assert set(prior) == {
        "USGS3DEP:USGS_1M_19_x81y203_PR_PuertoRicoUSVI_D24",
        "USGS3DEP:USGS_1m_x81y203_PR_PRVI_D_2018",
        "USGS3DEP:USGS_1m_x81y203_PR_PRVI_H_2018",
    }
    receipt = _load(REPO_ROOT / next(iter(prior.values()))["receipt"])
    recorded = {e["url"]: e for entries in receipt.values() for e in entries}
    for asset_id, entry in prior.items():
        asset = _asset(ledger, asset_id.split(":", 1)[1])
        source = recorded[asset["native_identity"]["source_url"]]
        assert entry["computed_sha256"] == source["sha256"]
        assert entry["size_agrees"] and entry["object_unchanged_since"]
        assert entry["bytes_held_in_this_checkout"] is False
        assert asset["integrity"]["computed_sha256"] is None


def test_dataset_identity_and_survey_window_match_the_elevation_catalogue(ledger):
    yaml = pytest.importorskip("yaml")
    catalogue = yaml.safe_load(
        (REPO_ROOT / discovery.DEM_CATALOG_PATH).read_text(encoding="utf-8")
    )
    products = {p["source_id"]: p for p in catalogue["products"]}
    conflicts = {c["conflict_id"] for c in catalogue["registry_conflicts"]}
    assert "3dep_vertical_datum_label" in conflicts
    for dataset_id, (catalog_id, window) in discovery.DATASET_CATALOG.items():
        product = products[catalog_id]
        assert (
            product["acquisition_window"]["start"],
            product["acquisition_window"]["end"],
        ) == window
        assert product["vertical_datum"] == "NAVD88"
    for asset in ledger["assets"]:
        assert asset["dataset_catalog_id"] in products
        assert (
            asset["temporal"]["observation_start"]
            < asset["temporal"]["observation_end"]
        )
