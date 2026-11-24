"""DEM platform catalog: schema, registration accounting, datum parity, conflicts, docs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from gebco.marine_evidence import SensorType  # noqa: E402
from source_adapters.dem_platform.catalog import (  # noqa: E402
    PLATFORM_CLASSES,
    Registration,
    account,
    check_observation,
    datum_parity_failures,
    group_by_platform_class,
    load_catalog,
    products_by_id,
    registration_universe,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "sources" / "dem_sources_by_platform.md"


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog()


def test_catalog_validates_and_ids_are_unique(catalog: dict) -> None:
    ids = [p["source_id"] for p in catalog["products"]]
    assert len(ids) == len(set(ids))
    assert set(group_by_platform_class(catalog)) == set(PLATFORM_CLASSES)


def test_every_registration_is_accounted_for(catalog: dict) -> None:
    acc = account(catalog)
    assert acc.unaccounted == (), f"add these to the catalog as aliases or non-products: {acc.unaccounted}"
    assert acc.stale == (), f"catalog references no extractor finds: {acc.stale}"
    assert acc.double_counted == ()
    assert acc.as_dict()["accounted_percent"] == 100.0


def test_universe_counts_are_pinned(catalog: dict) -> None:
    # Pinned so a new registration shows up as a reviewed change, not silently.
    universe = registration_universe()
    assert len(universe) == 71
    assert len({r.path for r in universe}) == 22
    assert sum(len(p["aliases"]) for p in catalog["products"]) == 52
    assert len(catalog["non_product_registrations"]) == 19


def test_known_duplicates_collapse_to_one_product(catalog: dict) -> None:
    products = products_by_id(catalog)
    cudem_third = {(a["path"], a["id"]) for a in products["ncei_puerto_rico_cudem_third_9524"]["aliases"]}
    assert cudem_third == {
        ("data_sources/noaa/ncei_coastal_dems.yml", "puerto_rico_cudem_third_9524"),
        ("data/ncei_coastal_dem/registry/ncei_coastal_dem_priority_datasets.csv", "puerto_rico_cudem_13"),
        ("pipeline/pr_marine_datasets.py", "9524"),
    }
    assert len(products["usgs_3dep_1m_pr_prvi_2018"]["aliases"]) == 10


def test_alias_paths_exist(catalog: dict) -> None:
    for product in catalog["products"]:
        for alias in product["aliases"]:
            assert (REPO_ROOT / alias["path"]).exists(), alias
    for entry in catalog["non_product_registrations"]:
        assert (REPO_ROOT / entry["path"]).exists(), entry


def test_authority_datums_match_their_manifests(catalog: dict) -> None:
    assert datum_parity_failures(catalog) == []


def test_registry_conflicts_still_hold(catalog: dict) -> None:
    for conflict in catalog["registry_conflicts"]:
        if conflict["status"] != "open":
            continue
        for obs in conflict["observations"]:
            assert check_observation(obs), (
                f"{conflict['conflict_id']}: {obs['path']} {obs['id']} no longer shows this; "
                "if the conflict was fixed, mark it resolved in the catalog"
            )


def test_observation_checks_on_lidar_config_and_receipt(tmp_path: Path) -> None:
    config = {"sites": [{"site_id": "s1", "lidar_2018": [{"project": "PR_PRVI_A_2018", "stated_vertical_datum": "NAVD88"}],
                         "lidar_d24": {"project": "PR_PuertoRicoUSVI_D24", "stated_vertical_datum": "NAVD88"}}]}
    receipt = {"datum_test_lidar_2018_minus_cudem_ninth_low_slope": {"s1": {"median_m": -0.12}, "s2": None}}
    (tmp_path / "tiles.json").write_text(json.dumps(config))
    (tmp_path / "comparison.json").write_text(json.dumps(receipt))
    assert check_observation({"path": "tiles.json", "id": "PR_PRVI_A_2018", "field": "stated_vertical_datum",
                              "value": "NAVD88", "check": "equals"}, tmp_path)
    near = {"path": "comparison.json", "id": "s1", "field": "median_m", "check": "abs_at_most"}
    assert check_observation({**near, "value": 0.15}, tmp_path)
    assert not check_observation({**near, "value": 0.1}, tmp_path)
    assert not check_observation({**near, "id": "s2", "value": 0.15}, tmp_path)  # no test at that site


def test_sensor_types_use_the_existing_vocabulary(catalog: dict) -> None:
    allowed = {s.value for s in SensorType}
    for product in catalog["products"]:
        assert product["sensor_type"] is None or product["sensor_type"] in allowed, product["source_id"]


def test_catalog_only_products_are_lineage_nodes(catalog: dict) -> None:
    for product in catalog["products"]:
        if product.get("registration_status") == "catalog_only":
            assert product["aliases"] == []
            assert product["consumed_by"], product["source_id"]


def test_consumed_by_provider_refs_resolve(catalog: dict) -> None:
    import yaml

    for product in catalog["products"]:
        for consumer in product["consumed_by"]:
            path, _, key = consumer["provider_ref"].partition("#")
            providers = yaml.safe_load((REPO_ROOT / path).read_text())["providers"]
            assert key in providers, consumer["provider_ref"]


def test_adapter_configs_point_at_catalog_entries(catalog: dict) -> None:
    products = products_by_id(catalog)
    ot = json.loads((REPO_ROOT / "data_sources/opentopography/globaldem.yml").read_text())
    for entry in ot["demtypes"]:
        assert entry["catalog_source_id"] in products
        assert Registration("data_sources/opentopography/globaldem.yml", entry["demtype"]) in {
            Registration(a["path"], a["id"]) for a in products[entry["catalog_source_id"]]["aliases"]
        }


def test_srtm_family_shares_one_root_despite_platform_names(catalog: dict) -> None:
    products = products_by_id(catalog)
    srtm, nasadem = products["nasa_srtmgl1_v003"], products["nasa_nasadem_hgt_v001"]
    assert srtm["platforms"][0]["short_name"] == "STS-99"
    assert nasadem["platforms"][0]["short_name"] == "OV-105"
    root = "srtm:sts-99:2000-02"
    for sid in ("nasa_srtmgl1_v003", "nasa_nasadem_hgt_v001", "gebco_2023"):
        assert {"root_id": root, "kind": "measurement"} in products[sid]["acquisition_roots"], sid


def test_doc_lists_every_product_and_conflict(catalog: dict) -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    for product in catalog["products"]:
        assert f"`{product['source_id']}`" in text, product["source_id"]
    for conflict in catalog["registry_conflicts"]:
        assert f"`{conflict['conflict_id']}`" in text, conflict["conflict_id"]


def test_cop30_and_aw3d30_datums_are_cited(catalog: dict) -> None:
    products = products_by_id(catalog)
    receipt_path = REPO_ROOT / "evidence" / "dem_sources" / "vertical_datums_2026-11-24" / "datum_check.json"
    receipt = json.loads(receipt_path.read_text())
    for sid, datum, epsg in (("copernicus_glo30_dem", "EGM2008", "3855"), ("jaxa_aw3d30", "EGM96", "5773")):
        product = products[sid]
        basis = product["vertical_datum_basis"]
        assert product["vertical_datum"] == datum
        assert basis["evidence_tier"] == "T1"
        assert (REPO_ROOT / basis["receipt"]) == receipt_path
        assert any(epsg in s["statement"] for s in basis["sources"]), sid
    assert any("ESA" in s["source"] for s in products["copernicus_glo30_dem"]["vertical_datum_basis"]["sources"])
    assert products["jaxa_aw3d30"]["vertical_datum_basis"]["not_retrieved"]
    assert receipt["findings"]["COP30"]["vertical_datum"] == "EGM2008"
    assert receipt["findings"]["AW3D30"]["vertical_datum"] == "EGM96"


def test_geoid_offset_receipt_is_consistent() -> None:
    receipt = json.loads((REPO_ROOT / "evidence" / "dem_sources" / "vertical_datums_2026-11-24" / "datum_check.json").read_text())
    geo = receipt["geoid_offset"]
    dn = geo["geoid_difference_N_egm2008_minus_N_egm96_m"]
    assert dn["min"] <= dn["mean"] <= dn["max"] and abs(dn["max"]) < 2 and abs(dn["min"]) < 2
    assert "EGM2008 height (1)" in geo["transformation"] and "EGM96 height (1)" in geo["transformation"]
    before, after = geo["cop30_minus_srtmgl1_as_published"], geo["cop30_on_egm96_minus_srtmgl1"]
    # A geoid shift moves the offset, not the spread.
    assert after["std_m"] == pytest.approx(before["std_m"], abs=0.05)
    assert after["median_m"] > before["median_m"]
