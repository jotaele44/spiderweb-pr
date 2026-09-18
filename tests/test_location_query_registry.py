from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/location_query_providers.json"
CONTRACT = ROOT / "schemas/location_query.schema.json"

EXPECTED_PROVIDERS = {
    "USGS_3DEP_1M",
    "PRVI_1m_DEM_2018",
    "NCEI_COASTAL_DEM",
    "NASA_GIBS_IMAGERY",
    "SENTINEL_HUB_IMAGERY",
    "COPERNICUS_CDSE_IMAGERY",
    "PRPB_GEOLOGY_KARST",
    "PR_AQUIFERS_WELLS_SPRINGS",
    "PR_MARINE_LIDAR_TOPOBATHY",
    "SSURGO_SOILS",
    "USGS_3DHP_NHD",
    "USFWS_NWI",
    "FEMA_NFHL",
    "FEMA_PR_ABFE_1PCT",
    "USACE_GENERAL_GIS",
    "USACE_PORTS_NAV",
}


def test_provider_registry_references_existing_contract() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert payload["contract"] == "schemas/location_query.schema.json"
    assert CONTRACT.is_file()


def test_provider_status_and_query_modes_are_bounded() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    allowed_status = set(payload["readiness_states"])
    allowed_modes = {"point", "radius", "bbox", "polygon", "geojson"}
    providers = payload["providers"]
    assert set(providers) == EXPECTED_PROVIDERS
    assert len(providers) == 16
    for provider_id, provider in providers.items():
        assert provider["status"] in allowed_status, provider_id
        modes = provider.get("query_modes")
        assert isinstance(modes, list) and modes, provider_id
        assert set(modes) <= allowed_modes, provider_id


def test_ready_routes_bind_to_existing_implementation_files() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    expected_paths = {
        "USGS_3DEP_1M": ["tools/source_manifestation_seed.py", "tools/spatial_aoi_fetcher.py"],
        "NCEI_COASTAL_DEM": ["source_adapters/ncei_coastal_dem/cli.py"],
        "NASA_GIBS_IMAGERY": ["imagery/providers/gibs.py"],
        "SENTINEL_HUB_IMAGERY": ["imagery/providers/sentinelhub.py"],
        "COPERNICUS_CDSE_IMAGERY": ["imagery/providers/copernicus.py"],
        "PRPB_GEOLOGY_KARST": ["spiderweb/subsurface/sources.py", "spiderweb/location_query_sources.py"],
        "PR_AQUIFERS_WELLS_SPRINGS": ["spiderweb/subsurface/sources.py", "spiderweb/location_query_sources.py"],
        "PR_MARINE_LIDAR_TOPOBATHY": ["pipeline/pr_marine_datasets.py"],
        "SSURGO_SOILS": ["spiderweb/location_query_sources.py"],
        "USGS_3DHP_NHD": ["spiderweb/location_query_sources.py"],
        "USFWS_NWI": ["spiderweb/location_query_sources.py"],
        "FEMA_NFHL": ["spiderweb/location_query_sources.py"],
        "FEMA_PR_ABFE_1PCT": ["spiderweb/location_query_sources.py"],
        "USACE_GENERAL_GIS": ["spiderweb/location_query_sources.py"],
        "USACE_PORTS_NAV": ["spiderweb/location_query_sources.py"],
    }
    for provider_id, paths in expected_paths.items():
        assert provider_id in payload["providers"]
        for path in paths:
            assert (ROOT / path).is_file(), (provider_id, path)


def test_incomplete_families_remain_explicit_without_false_promotion() -> None:
    providers = json.loads(REGISTRY.read_text(encoding="utf-8"))["providers"]
    assert providers["SSURGO_SOILS"]["status"] == "RESOLVER_ONLY"
    assert providers["USGS_3DHP_NHD"]["status"] == "RESOLVER_ONLY"
    assert providers["FEMA_NFHL"]["status"] == "RESOLVER_ONLY"
    assert providers["FEMA_PR_ABFE_1PCT"]["status"] == "RESOLVER_ONLY"
    assert providers["USACE_GENERAL_GIS"]["status"] == "RESOLVER_ONLY"
    assert providers["PRVI_1m_DEM_2018"]["status"] == "PROVIDER_BINDING_OPEN"


def test_promoted_specialized_routes_have_bounded_machine_surfaces() -> None:
    providers = json.loads(REGISTRY.read_text(encoding="utf-8"))["providers"]
    assert providers["USFWS_NWI"]["status"] == "READY_SPECIALIZED"
    assert providers["USFWS_NWI"]["layer_url"].endswith("/Wetlands/FeatureServer/0")
    assert providers["USACE_PORTS_NAV"]["status"] == "READY_SPECIALIZED"
    layers = providers["USACE_PORTS_NAV"]["layers"]
    assert len(layers) == 4
    assert len({row["role"] for row in layers}) == 4
