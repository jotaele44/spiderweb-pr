#!/usr/bin/env python3
"""Offline invariant audit for the canonical LOCATION_QUERY provider registry."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/location_query_providers.json"
REFERENCE_AOIS = ROOT / "configs/location_query_reference_aois.json"

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

PATH_BINDINGS = {
    "USGS_3DEP_1M": ["tools/source_manifestation_seed.py", "tools/spatial_aoi_fetcher.py"],
    "PRVI_1m_DEM_2018": ["tools/spatial_aoi_fetcher.py"],
    "NCEI_COASTAL_DEM": ["source_adapters/ncei_coastal_dem/cli.py"],
    "NASA_GIBS_IMAGERY": ["imagery/providers/gibs.py"],
    "SENTINEL_HUB_IMAGERY": ["imagery/providers/sentinelhub.py"],
    "COPERNICUS_CDSE_IMAGERY": ["imagery/providers/copernicus.py"],
    "PRPB_GEOLOGY_KARST": ["spiderweb/subsurface/sources.py"],
    "PR_AQUIFERS_WELLS_SPRINGS": ["spiderweb/subsurface/sources.py"],
    "PR_MARINE_LIDAR_TOPOBATHY": ["pipeline/pr_marine_datasets.py"],
    "SSURGO_SOILS": ["spiderweb/location_query_sources.py", "spiderweb/ssurgo_chain.py", "scripts/location_query_fetch.py"],
    "USGS_3DHP_NHD": ["spiderweb/location_query_sources.py", "spiderweb/provider_denominators.py"],
    "USFWS_NWI": ["spiderweb/location_query_sources.py", "scripts/location_query_fetch.py"],
    "FEMA_NFHL": ["spiderweb/location_query_sources.py", "spiderweb/provider_denominators.py"],
    "FEMA_PR_ABFE_1PCT": ["spiderweb/location_query_sources.py", "spiderweb/provider_denominators.py", "spiderweb/denominator_chain.py"],
    "USACE_GENERAL_GIS": ["spiderweb/location_query_sources.py", "spiderweb/provider_denominators.py", "spiderweb/denominator_chain.py"],
    "USACE_PORTS_NAV": ["spiderweb/location_query_sources.py", "scripts/location_query_fetch.py"],
}


def main() -> int:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        raise SystemExit("FAIL: providers missing")
    actual = set(providers)
    if actual != EXPECTED_PROVIDERS:
        raise SystemExit(
            f"FAIL: provider denominator drift; missing={sorted(EXPECTED_PROVIDERS-actual)} extra={sorted(actual-EXPECTED_PROVIDERS)}"
        )
    states = set(payload.get("readiness_states", []))
    if not states:
        raise SystemExit("FAIL: readiness state denominator missing")
    for provider_id, provider in providers.items():
        if provider.get("status") not in states:
            raise SystemExit(f"FAIL: invalid status for {provider_id}")
        modes = provider.get("query_modes")
        if not isinstance(modes, list) or not modes:
            raise SystemExit(f"FAIL: query_modes missing for {provider_id}")
    missing_paths: list[str] = []
    for provider_id, paths in PATH_BINDINGS.items():
        for path in paths:
            if not (ROOT / path).is_file():
                missing_paths.append(f"{provider_id}:{path}")
    if missing_paths:
        raise SystemExit(f"FAIL: implementation bindings missing: {missing_paths}")
    aois = json.loads(REFERENCE_AOIS.read_text(encoding="utf-8")).get("reference_aois")
    if not isinstance(aois, list) or len(aois) != 3:
        raise SystemExit("FAIL: reference AOI denominator != 3")
    if len({row.get("id") for row in aois}) != 3:
        raise SystemExit("FAIL: reference AOI ids not unique")
    counts: dict[str, int] = {}
    for provider in providers.values():
        state = provider["status"]
        counts[state] = counts.get(state, 0) + 1
    print(json.dumps({
        "state": "PASS",
        "provider_count": len(providers),
        "readiness_counts": dict(sorted(counts.items())),
        "reference_aoi_count": len(aois),
        "implementation_binding_count": sum(len(v) for v in PATH_BINDINGS.values()),
        "network_requests": 0,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
