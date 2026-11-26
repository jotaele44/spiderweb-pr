"""Merge policy and independence rules for DEM sources by acquisition platform."""

from __future__ import annotations

import copy

import pytest

pytest.importorskip("jsonschema")

from source_adapters.dem_platform.catalog import (  # noqa: E402
    load_catalog,
    products_by_id,
)
from source_adapters.dem_platform.policy import (  # noqa: E402
    evaluate_platform_mix,
    geolocation_dependencies,
    independent,
    layer_groups,
    pairwise_independence,
    shared_acquisition_roots,
)

LANDSAT = "configs/remote_monitoring/providers.yaml#landsat_archive"


@pytest.fixture(scope="module")
def products() -> dict:
    return products_by_id(load_catalog())


def test_empty_selection_needs_review() -> None:
    result = evaluate_platform_mix([])
    assert result.merge_policy == "no_sources"
    assert result.review_status == "review_required"


def test_single_verified_source_passes(products: dict) -> None:
    result = evaluate_platform_mix([products["nasa_srtmgl1_v003"]])
    assert (result.merge_policy, result.review_status) == ("single_source", "pass")


def test_spaceborne_and_airborne_stay_separate(products: dict) -> None:
    result = evaluate_platform_mix([products["nasa_srtmgl1_v003"], products["usgs_3dep_1m_pr_prvi_2018"]])
    assert result.merge_policy == "separate_layers_until_harmonization"
    assert result.review_status == "review_required"
    joined = " | ".join(result.reasons)
    assert "mixed platform classes" in joined
    assert "mixed surface models" in joined
    assert "mixed vertical datums" in joined


def test_two_lidar_epochs_stay_separate_layers_of_one_group(products: dict) -> None:
    # Both are PRVD02, reached through different geoids (2018: GEOID12B, D24: GEOID18).
    result = evaluate_platform_mix([products["usgs_3dep_1m_pr_prvi_2018"], products["usgs_3dep_1m_pr_puertoricousvi_d24"]])
    assert result.review_status == "pass"
    assert result.merge_policy == "same_datum_separate_geoid_layers"
    assert result.vertical_datums == ("PRVD02",)
    assert result.geoid_models == ("GEOID12B", "GEOID18")
    assert result.reasons == ()
    assert result.notes and "difference them before any merge" in result.notes[0]


def test_same_geoid_products_merge_as_before(products: dict) -> None:
    d24 = products["usgs_3dep_1m_pr_puertoricousvi_d24"]
    twin = copy.deepcopy(d24)
    twin["source_id"] = "d24_twin"
    result = evaluate_platform_mix([d24, twin])
    assert result.merge_policy == "same_platform_class_same_surface_same_datum"
    assert result.notes == ()


def test_undeclared_geoid_counts_as_a_separate_realization(products: dict) -> None:
    d24 = products["usgs_3dep_1m_pr_puertoricousvi_d24"]
    unknown = copy.deepcopy(d24)
    unknown["source_id"], unknown["geoid_model"] = "d24_unknown_geoid", None
    result = evaluate_platform_mix([d24, unknown])
    assert result.merge_policy == "same_datum_separate_geoid_layers"
    assert result.geoid_models == ("GEOID18", "undeclared")


def test_layer_groups_split_by_geoid_within_one_group(products: dict) -> None:
    selected = [products[i] for i in ("usgs_3dep_1m_pr_prvi_2018", "usgs_3dep_1m_pr_puertoricousvi_d24", "nasa_srtmgl1_v003")]
    groups = layer_groups(selected)
    assert groups[("airborne", "bare_earth", "PRVD02")] == {
        "GEOID12B": ("usgs_3dep_1m_pr_prvi_2018",), "GEOID18": ("usgs_3dep_1m_pr_puertoricousvi_d24",)}
    assert groups[("spaceborne", "radar_scattering_surface", "EGM96")] == {"undeclared": ("nasa_srtmgl1_v003",)}


def test_policy_dict_keeps_its_keys(products: dict) -> None:
    d = evaluate_platform_mix([products["nasa_srtmgl1_v003"]]).as_dict()
    assert {"source_ids", "platform_classes", "surface_models", "vertical_datums", "merge_policy", "review_status", "reasons"} <= d.keys()
    assert d["geoid_models"] == ["undeclared"] and d["notes"] == []


def test_compiled_products_are_never_merged_as_independent(products: dict) -> None:
    result = evaluate_platform_mix([products["ncei_arecibo_2007"], products["ncei_ponce_2007"]])
    assert result.review_status == "review_required"
    assert any("compiled products" in r for r in result.reasons)


def test_undeclared_datum_fails_closed(products: dict) -> None:
    # The 2004 USACE lidar states "User Specified"; its datum is not known.
    result = evaluate_platform_mix([products["usace_lidar_2004_pr"]])
    assert result.review_status == "review_required"
    assert any("vertical datum undeclared" in r for r in result.reasons)


def test_cop30_and_srtm_differ_only_by_geoid(products: dict) -> None:
    # Both are spaceborne radar surfaces; only the geoid differs (EGM2008 vs EGM96).
    result = evaluate_platform_mix([products["copernicus_glo30_dem"], products["nasa_srtmgl1_v003"]])
    assert result.review_status == "review_required"
    assert result.reasons == ("mixed vertical datums: EGM2008, EGM96",)


def test_aw3d30_alone_passes_now_its_datum_is_known(products: dict) -> None:
    result = evaluate_platform_mix([products["jaxa_aw3d30"]])
    assert (result.merge_policy, result.review_status) == ("single_source", "pass")


def test_unverified_platform_fails_closed(products: dict) -> None:
    unverified = copy.deepcopy(products["nasa_srtmgl1_v003"])
    unverified["platform_status"] = "unverified"
    result = evaluate_platform_mix([unverified])
    assert result.review_status == "review_required"
    assert any("not verified" in r for r in result.reasons)


def test_srtm_and_gebco_share_the_shuttle_root(products: dict) -> None:
    assert shared_acquisition_roots(products["nasa_srtmgl1_v003"], products["gebco_2023"]) == ("srtm:sts-99:2000-02",)
    assert not independent(products["nasa_srtmgl1_v003"], products["gebco_2023"])


def test_srtm_and_nasadem_are_not_independent(products: dict) -> None:
    assert "srtm:sts-99:2000-02" in shared_acquisition_roots(products["nasa_srtmgl1_v003"], products["nasa_nasadem_hgt_v001"])


def test_srtm_and_3dep_2018_are_independent(products: dict) -> None:
    assert independent(products["nasa_srtmgl1_v003"], products["usgs_3dep_1m_pr_prvi_2018"])
    assert independent(products["nasa_srtmgl1_v003"], products["copernicus_glo30_dem"])


def test_3dep_2018_dem_shares_its_lidar_root(products: dict) -> None:
    shared = shared_acquisition_roots(products["usgs_3dep_1m_pr_prvi_2018"], products["usgs_lidar_2018_hurricane_maria"])
    assert shared == ("usiei:933E88E7-A131-40E5-8BAA-C9575216E040",)


def test_fill_roots_count_unless_excluded(products: dict) -> None:
    srtm, nasadem = products["nasa_srtmgl1_v003"], products["nasa_nasadem_hgt_v001"]
    assert "aster:terra:gdem2" in shared_acquisition_roots(srtm, nasadem)
    assert "aster:terra:gdem2" not in shared_acquisition_roots(srtm, nasadem, kinds=("measurement",))


def test_landsat_depends_on_gls2000_for_geolocation_only(products: dict) -> None:
    gls = products["usgs_gls2000_dem"]
    deps = geolocation_dependencies(gls, LANDSAT)
    assert len(deps) == 1 and deps[0]["dependency_kind"] == "geolocation"
    assert "GLS2000" in deps[0]["evidence"]
    # The dependency is not an acquisition root, so it never breaks independence.
    assert all(r["kind"] != "geolocation" for r in products["nasa_srtmgl1_v003"]["acquisition_roots"])


def test_pairwise_independence_rows(products: dict) -> None:
    rows = pairwise_independence([products["nasa_srtmgl1_v003"], products["gebco_2023"], products["jaxa_aw3d30"]])
    assert [(r["a"], r["b"], r["independent"]) for r in rows] == [
        ("nasa_srtmgl1_v003", "gebco_2023", False),
        ("nasa_srtmgl1_v003", "jaxa_aw3d30", True),
        ("gebco_2023", "jaxa_aw3d30", True),
    ]
