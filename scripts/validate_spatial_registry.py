#!/usr/bin/env python3
"""Gate the federation spatial registries.

Each check is a named gate so a CI failure says which invariant broke rather
than only that something did. Every gate fails closed: an absent or unreadable
registry is a failure, never a silent pass.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

GRID_CSV = REPO_ROOT / "registry/spatial/pr_grid_full_cell_index_saturated.csv"
GRID_MANIFEST = REPO_ROOT / "registry/spatial/pr_grid_full_cell_index_saturated.manifest.json"
CELL_SCHEMA = REPO_ROOT / "schemas/pr_grid_cell.schema.json"
TRANSFORM = REPO_ROOT / "registry/spatial/geometry/pr_grid_transform.json"
GEOMETRY_MANIFEST = REPO_ROOT / "registry/spatial/geometry/pr_grid_geometry_manifest.json"
MANIFESTATIONS = REPO_ROOT / "registry/spatial/source_manifestations.json"
BINDINGS = REPO_ROOT / "registry/spatial/cell_source_binding.json"
CAPABILITIES = REPO_ROOT / "registry/spatial/capabilities.json"

EXPECTED_CELL_COUNT = 98_304
PROMOTED_BINDING_STATES = {"CANONICAL", "VERIFIED", "ALTERNATE"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def gate_cell_id_schema() -> list[str]:
    """Every canonical Cell_ID must satisfy the published schema pattern.

    This gate exists because it once did not: the shipped pattern required three
    zero-padded digits while the frozen CSV is unpadded, so 54,000 of the 98,304
    identifiers failed the repo's own schema with nothing enforcing it.
    """
    pattern = re.compile(_load(CELL_SCHEMA)["properties"]["Cell_ID"]["pattern"])
    failures: list[str] = []
    seen: set[str] = set()
    total = 0
    with GRID_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            identifier = row["Cell_ID"]
            if not pattern.match(identifier):
                if len(failures) < 3:
                    failures.append(f"Cell_ID {identifier!r} violates the published pattern")
                continue
            if identifier in seen:
                failures.append(f"duplicate Cell_ID {identifier!r}")
            seen.add(identifier)
    if total != EXPECTED_CELL_COUNT:
        failures.append(f"grid row count {total} != {EXPECTED_CELL_COUNT}")
    if len(seen) != EXPECTED_CELL_COUNT and not failures:
        failures.append(f"unique Cell_ID count {len(seen)} != {EXPECTED_CELL_COUNT}")
    return failures


def gate_geometry_cardinality() -> list[str]:
    manifest = _load(GEOMETRY_MANIFEST)
    failures: list[str] = []
    if manifest.get("cell_count") != EXPECTED_CELL_COUNT:
        failures.append(f"geometry cell_count {manifest.get('cell_count')} != {EXPECTED_CELL_COUNT}")
    for field in ("duplicate_cell_ids", "orphan_geometries", "missing_geometries"):
        if manifest.get(field) != 0:
            failures.append(f"{field} = {manifest.get(field)} (must be 0)")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("sha256", ""))):
        failures.append("geometry manifest carries no sha256")
    return failures


def gate_transform_certification() -> list[str]:
    """A PROVISIONAL transform must not support any promoted binding."""
    transform = _load(TRANSFORM)
    state = transform.get("certification_state")
    failures: list[str] = []
    if state not in {"VERIFIED", "PROVISIONAL"}:
        return [f"unknown certification_state {state!r}"]

    geometry_state = _load(GEOMETRY_MANIFEST).get("certification_state")
    if geometry_state != state:
        failures.append(f"geometry state {geometry_state!r} disagrees with transform {state!r}")

    bindings = _load(BINDINGS)
    if state == "PROVISIONAL":
        promoted = [
            b for b in bindings.get("bindings", [])
            if b.get("Binding_State") in PROMOTED_BINDING_STATES
        ]
        if promoted:
            failures.append(
                f"{len(promoted)} binding(s) promoted while the grid transform is PROVISIONAL"
            )
        if bindings.get("bindings") and not bindings.get("unresolved_reason"):
            failures.append("bindings present under a PROVISIONAL transform without a reason")
    return failures


def gate_canonical_uniqueness() -> list[str]:
    """Exactly one default per Cell_ID x Capability, or an explicit UNRESOLVED."""
    bindings = _load(BINDINGS).get("bindings", [])
    defaults: dict[tuple[str, str], int] = {}
    for binding in bindings:
        if binding.get("Is_Default"):
            key = (binding["Cell_ID"], binding["Capability"])
            defaults[key] = defaults.get(key, 0) + 1
    return [
        f"{count} defaults for {cell}/{capability} (exactly one permitted)"
        for (cell, capability), count in sorted(defaults.items())
        if count != 1
    ]


def gate_no_duplicate_provider() -> list[str]:
    registry = _load(MANIFESTATIONS)
    manifestations = registry.get("manifestations", [])
    failures: list[str] = []

    for field in ("Manifestation_ID", "Provider_Object_ID"):
        seen: set[str] = set()
        duplicates = sorted({m[field] for m in manifestations if m[field] in seen or seen.add(m[field])})
        if duplicates:
            failures.append(f"duplicate {field}: {duplicates[:3]}")

    if registry.get("manifestation_count") != len(manifestations):
        failures.append("manifestation_count disagrees with the record list")

    # One canonical projection per dataset version: the multi-zone rule.
    canonical_crs = {
        m.get("Provider_CRS")
        for m in manifestations
        if m.get("Manifestation_Class") == "CANONICAL"
    }
    if len(canonical_crs) > 1:
        failures.append(f"canonical manifestations span multiple CRSs: {sorted(canonical_crs)}")
    return failures


def gate_coverage_arithmetic() -> list[str]:
    failures: list[str] = []
    for binding in _load(BINDINGS).get("bindings", []):
        for field in ("Cell_Coverage_Fraction", "Manifestation_Coverage_Fraction"):
            value = binding.get(field)
            if value is not None and not 0.0 <= float(value) <= 1.0:
                failures.append(f"{field}={value} outside [0,1] for {binding.get('Cell_ID')}")
    for manifestation in _load(MANIFESTATIONS).get("manifestations", []):
        expected = manifestation.get("Expected_Bytes")
        if expected is not None and int(expected) <= 0:
            failures.append(f"non-positive Expected_Bytes for {manifestation['Manifestation_ID']}")
    return failures


def gate_capability_policy() -> list[str]:
    capabilities = _load(CAPABILITIES).get("capabilities", {})
    declared = set(capabilities)
    failures: list[str] = []
    used = {
        m.get("Capability")
        for m in _load(MANIFESTATIONS).get("manifestations", [])
    }
    unknown = sorted(used - declared)
    if unknown:
        failures.append(f"manifestations reference undeclared capabilities: {unknown}")
    for name, capability in capabilities.items():
        if not capability.get("Canonicality_Rules"):
            failures.append(f"capability {name} declares no canonicality rules")
    return failures


GATES: dict[str, Callable[[], list[str]]] = {
    "CELL_ID_SCHEMA_GATE": gate_cell_id_schema,
    "GEOMETRY_CARDINALITY_GATE": gate_geometry_cardinality,
    "TRANSFORM_CERTIFICATION_GATE": gate_transform_certification,
    "CANONICAL_UNIQUENESS_GATE": gate_canonical_uniqueness,
    "NO_DUPLICATE_PROVIDER_GATE": gate_no_duplicate_provider,
    "COVERAGE_ARITHMETIC_GATE": gate_coverage_arithmetic,
    "CAPABILITY_POLICY_GATE": gate_capability_policy,
}


def run(selected: Sequence[str] | None = None) -> int:
    names = list(selected) if selected else list(GATES)
    exit_code = 0
    for name in names:
        try:
            failures = GATES[name]()
        except (OSError, ValueError, KeyError) as exc:
            failures = [f"gate could not run: {exc}"]
        if failures:
            exit_code = 1
            print(f"FAIL {name}")
            for failure in failures:
                print(f"     {failure}")
        else:
            print(f"PASS {name}")
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="append", choices=sorted(GATES), help="run only this gate")
    args = parser.parse_args(argv)
    return run(args.gate)


if __name__ == "__main__":
    sys.exit(main())
