#!/usr/bin/env python3
"""Offline static certification gates for LOCATION_QUERY source and router files."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess

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
    ROOT / "scripts/location_query_ssurgo.py",
    ROOT / "spiderweb/ssurgo_chain.py",
    ROOT / "spiderweb/provider_denominators.py",
    ROOT / "spiderweb/denominator_chain.py",
    ROOT / "spiderweb/place_resolver.py",
    ROOT / "spiderweb/provider_promotion.py",
    ROOT / "spiderweb/reference_corpus.py",
    ROOT / "scripts/ssurgo_location_stage2.py",
    ROOT / "scripts/freeze_location_provider_denominator.py",
    ROOT / "scripts/build_location_denominator_stage.py",
    ROOT / "scripts/place_resolve.py",
    ROOT / "scripts/adjudicate_location_provider.py",
    ROOT / "scripts/merge_location_service_denominators.py",
    ROOT / "scripts/ssurgo_location_stage3.py",
    ROOT / "scripts/certify_ssurgo_child.py",
    ROOT / "scripts/run_location_query_reference_corpus.py",
    ROOT / "scripts/audit_location_query_provider_health.py",
    ROOT / "scripts/audit_location_query_static.py",
    ROOT / "tests/test_denominator_chain.py",
    ROOT / "tests/test_location_query.py",
    ROOT / "tests/test_location_query_fetch.py",
    ROOT / "tests/test_location_query_package.py",
    ROOT / "tests/test_location_query_reference_corpus.py",
    ROOT / "tests/test_location_query_registry.py",
    ROOT / "tests/test_location_query_sources.py",
    ROOT / "tests/test_place_resolver.py",
    ROOT / "tests/test_provider_denominators.py",
    ROOT / "tests/test_provider_promotion.py",
    ROOT / "tests/test_ssurgo_chain.py",
    ROOT / "spiderweb/denominator_closure.py",
    ROOT / "scripts/close_location_query_denominators.py",
    ROOT / "tests/test_denominator_closure.py",
    ROOT / "spiderweb/specialized_execution.py",
    ROOT / "scripts/location_query_specialized.py",
    ROOT / "tests/test_specialized_execution.py",
    ROOT / "spiderweb/execution_orchestrator.py",
    ROOT / "scripts/location_query_run.py",
    ROOT / "scripts/location_query_run_package.py",
    ROOT / "tests/test_execution_orchestrator.py",
]
REGISTRY = ROOT / "configs/location_query_providers.json"
BINDINGS = ROOT / "configs/location_query_source_bindings.json"
SHELL_FILES = [
    ROOT / "scripts/run_location_query_runtime_closure.sh",
]
SSURGO_CHILDREN = ROOT / "configs/ssurgo_component_children.json"
SSURGO_COMPAT = ROOT / "scripts/location_query_ssurgo.py"

EXPECTED_BOUND = {
    "SSURGO_SOILS",
    "USGS_3DHP_NHD",
    "USFWS_NWI",
    "FEMA_NFHL",
    "FEMA_PR_ABFE_1PCT",
    "USACE_GENERAL_GIS",
    "USACE_PORTS_NAV",
}

def main() -> int:
    syntax = {}
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        syntax[str(path.relative_to(ROOT))] = "PASS"

    shell_syntax = {}
    for path in SHELL_FILES:
        result = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"FAIL: shell syntax {path.relative_to(ROOT)}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        shell_syntax[str(path.relative_to(ROOT))] = "PASS"

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    providers = registry["providers"]
    bound = bindings["bindings"]
    ssurgo_children = json.loads(SSURGO_CHILDREN.read_text(encoding="utf-8"))
    ssurgo_compat_text = SSURGO_COMPAT.read_text(encoding="utf-8")

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
    if providers["USACE_GENERAL_GIS"]["status"] != "RESOLVER_ONLY":
        raise SystemExit("FAIL: USACE general must remain RESOLVER_ONLY until recursive service denominator closes")
    if providers["USACE_PORTS_NAV"]["status"] != "READY_SPECIALIZED":
        raise SystemExit("FAIL: USACE ports/navigation readiness drift")
    if bound["USGS_3DHP_NHD"]["status"] != "BOUND_FEATURE_SERVICE_DENOMINATOR_OPEN":
        raise SystemExit("FAIL: 3DHP binding must remain denominator-open")
    if bound["USACE_GENERAL_GIS"]["status"] != "BOUND_SERVICE_ROOT_DENOMINATOR_OPEN":
        raise SystemExit("FAIL: USACE general service-root binding state drift")

    child_rows = ssurgo_children.get("records")
    if ssurgo_children.get("schema_version") != "spiderweb.ssurgo_component_children.v1.1":
        raise SystemExit("FAIL: SSURGO child contract schema drift")
    if ssurgo_children.get("relationship_count") != 22:
        raise SystemExit("FAIL: current SSURGO component-child denominator != 22")
    if not isinstance(child_rows, list) or len(child_rows) != 22:
        raise SystemExit("FAIL: SSURGO child row conservation != 22")
    child_tables = [str(row.get("table", "")) for row in child_rows if isinstance(row, dict)]
    if len(child_tables) != 22 or len(set(child_tables)) != 22:
        raise SystemExit("FAIL: SSURGO child table uniqueness drift")
    if "coinundationtype" not in child_tables:
        raise SystemExit("FAIL: current SSURGO child denominator lacks coinundationtype")
    lineage = ssurgo_children.get("lineage") or {}
    if lineage.get("prior_frozen_relationship_count") != 21 or lineage.get("contradiction_class") != "TIME":
        raise SystemExit("FAIL: SSURGO 21->22 lineage adjudication drift")
    sources = ssurgo_children.get("documentation_sources") or {}
    if sources.get("freeze_state") != "URL_AND_EPOCH_BOUND_RAW_BYTES_OPEN":
        raise SystemExit("FAIL: SSURGO documentation freeze-state drift")
    if "NONCANONICAL_COMPATIBILITY" not in ssurgo_compat_text:
        raise SystemExit("FAIL: monolithic SSURGO compatibility classification missing")
    if "--allow-noncanonical-compat" not in ssurgo_compat_text:
        raise SystemExit("FAIL: monolithic SSURGO compatibility execution gate missing")

    result = {
        "state": "PASS",
        "syntax": syntax,
        "syntax_file_count": len(FILES),
        "shell_syntax": shell_syntax,
        "shell_syntax_file_count": len(SHELL_FILES),
        "provider_count": len(providers),
        "source_binding_count": len(bound),
        "ssurgo_component_child_count": len(child_rows),
        "ssurgo_prior_child_count": lineage.get("prior_frozen_relationship_count"),
        "ssurgo_compatibility_state": "NONCANONICAL_COMPATIBILITY",
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
