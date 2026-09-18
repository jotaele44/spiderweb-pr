#!/usr/bin/env python3
"""Offline static certification gates for LOCATION_QUERY source and router files."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "spiderweb/location_query.py",
    ROOT / "spiderweb/location_query_sources.py",
    ROOT / "scripts/location_query.py",
    ROOT / "scripts/location_query_fetch.py",
    ROOT / "scripts/location_query_geocode.py",
    ROOT / "scripts/audit_location_query_registry.py",
    ROOT / "scripts/location_query_package.py",
    ROOT / "scripts/location_query_provider_health.py",
    ROOT / "scripts/location_query_usace_inventory.py",
    ROOT / "spiderweb/ssurgo_chain.py",
    ROOT / "spiderweb/provider_denominators.py",
    ROOT / "spiderweb/denominator_chain.py",
    ROOT / "spiderweb/place_resolver.py",
    ROOT / "spiderweb/provider_promotion.py",
    ROOT / "scripts/ssurgo_location_stage2.py",
    ROOT / "scripts/freeze_location_provider_denominator.py",
    ROOT / "scripts/build_location_denominator_stage.py",
    ROOT / "scripts/place_resolve.py",
    ROOT / "scripts/adjudicate_location_provider.py",
]
REGISTRY = ROOT / "configs/location_query_providers.json"
BINDINGS = ROOT / "configs/location_query_source_bindings.json"

EXPECTED_BOUND = {
    "SSURGO_SOILS",
    "USGS_3DHP_NHD",
    "USFWS_NWI",
    "FEMA_NFHL",
    "FEMA_PR_ABFE_1PCT",
    "USACE_PORTS_NAV",
}

def main() -> int:
    syntax = {}
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        syntax[str(path.relative_to(ROOT))] = "PASS"

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    providers = registry["providers"]
    bound = bindings["bindings"]

    if len(providers) != 16:
        raise SystemExit(f"FAIL: provider denominator != 16; got {len(providers)}")

    if not EXPECTED_BOUND <= set(bound):
        raise SystemExit(f"FAIL: missing source bindings {sorted(EXPECTED_BOUND-set(bound))}")
    if not EXPECTED_BOUND <= set(providers):
        raise SystemExit(f"FAIL: bound sources absent from provider registry {sorted(EXPECTED_BOUND-set(providers))}")

    if providers["SSURGO_SOILS"]["status"] != "RESOLVER_ONLY":
        raise SystemExit("FAIL: SSURGO must remain RESOLVER_ONLY until tabular chain closes")
    if providers["USGS_3DHP_NHD"]["status"] != "RESOLVER_ONLY":
        raise SystemExit("FAIL: 3DHP must remain RESOLVER_ONLY until frozen raw metadata denominator closes")
    if providers["USGS_3DHP_NHD"].get("denominator_state") != "OPEN_RAW_METADATA_FREEZE":
        raise SystemExit("FAIL: 3DHP denominator state drift")
    if providers["FEMA_NFHL"]["status"] != "RESOLVER_ONLY":
        raise SystemExit("FAIL: FEMA NFHL must remain RESOLVER_ONLY until vector denominator closes")
    if providers["FEMA_PR_ABFE_1PCT"]["status"] != "RESOLVER_ONLY":
        raise SystemExit("FAIL: FEMA Puerto Rico ABFE must remain RESOLVER_ONLY until layer denominator closes")
    if providers["USFWS_NWI"]["status"] != "READY_SPECIALIZED":
        raise SystemExit("FAIL: NWI readiness drift")
    if providers["USACE_PORTS_NAV"]["status"] != "READY_SPECIALIZED":
        raise SystemExit("FAIL: USACE ports/navigation readiness drift")

    result = {
        "state": "PASS",
        "syntax": syntax,
        "provider_count": len(providers),
        "source_binding_count": len(bound),
        "bounded_ready_specialized": sorted(
            key for key, value in providers.items()
            if value["status"] == "READY_SPECIALIZED"
        ),
        "resolver_only": sorted(
            key for key, value in providers.items()
            if value["status"] == "RESOLVER_ONLY"
        ),
        "network_requests": 0,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
