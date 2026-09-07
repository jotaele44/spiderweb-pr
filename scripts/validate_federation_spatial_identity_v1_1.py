#!/usr/bin/env python3
"""Structural and certification validator for federation-spatial-contract/1.1.

Default mode validates structural/cardinality/identity invariants. --certify also
requires zero unresolved residue and a non-empty frozen registry.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/federation_spatial_identity_v1_1.schema.json"
REGISTRY = ROOT / "registry/spatial/federation_spatial_identity_v1_1.json"
ALLOWED_CARDINALITY = {"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"}
ALLOWED_SPATIAL = {
    "FULLY_WITHIN",
    "PARTIAL",
    "TOUCH_ONLY",
    "OUTSIDE",
    "NULL_EMPTY",
    "UNRESOLVED",
}
FORBIDDEN_SOLE_IDENTITY = {
    "NAME_ONLY",
    "NORMALIZED_NAME_ONLY",
    "COUNT_EQUALITY",
    "NEAREST_ONLY",
    "PROXIMITY_ONLY",
    "SAME_CATEGORY",
    "SOURCE_ABSENCE",
}
CERTIFICATION_STATES = {
    "PASS",
    "FAIL",
    "OPEN",
    "BLOCKED",
    "PROVISIONAL",
    "AUDIT_ONLY",
    "NONCANONICAL",
    "CANDIDATE_NOT_IDENTITY",
    "UNRESOLVED",
    "SUPERSEDED",
}
TOP_LEVEL_FIELDS = {
    "contract_version",
    "source_manifestations",
    "geometry_manifestations",
    "canonical_entities",
    "identity_bindings",
    "unresolved",
}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicate_values: set[str] = set()
    for value in values:
        if value in seen:
            duplicate_values.add(value)
        seen.add(value)
    return sorted(duplicate_values)


def non_empty_exact_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def object_rows(
    data: Mapping[str, Any], field: str, problems: list[str]
) -> list[Mapping[str, Any]]:
    value = data.get(field)
    if not isinstance(value, list):
        problems.append(f"{field} must be an array")
        return []
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            problems.append(f"{field}[{index}] must be an object")
        else:
            rows.append(row)
    return rows


def identifiers(
    rows: list[Mapping[str, Any]], field: str, label: str, problems: list[str]
) -> list[str]:
    values: list[str] = []
    for index, row in enumerate(rows):
        value = row.get(field)
        if not non_empty_exact_string(value):
            problems.append(
                f"{label}[{index}] {field} must be a non-empty exact string"
            )
        else:
            values.append(value)
    duplicate_values = duplicates(values)
    if duplicate_values:
        problems.append(f"duplicate {label} ids: {duplicate_values}")
    return values


def reference_ids(
    row: Mapping[str, Any], field: str, label: str, problems: list[str]
) -> list[str]:
    values = row.get(field)
    if not isinstance(values, list):
        problems.append(f"{label} {field} must be an array")
        return []
    valid: list[str] = []
    for index, value in enumerate(values):
        if not non_empty_exact_string(value):
            problems.append(
                f"{label} {field}[{index}] must be a non-empty exact string"
            )
        else:
            valid.append(value)
    duplicate_values = duplicates(valid)
    if duplicate_values:
        problems.append(f"{label} {field} contains duplicates: {duplicate_values}")
    return valid


def validate_registry(data: Any, schema: Any, *, certify: bool = False) -> list[str]:
    problems: list[str] = []
    if not isinstance(schema, Mapping):
        problems.append("schema root must be an object")
    else:
        if (
            schema.get("$id")
            != "https://federation.local/schemas/federation_spatial_identity_v1_1.schema.json"
        ):
            problems.append("schema $id mismatch")
        if (
            schema.get("properties", {}).get("contract_version", {}).get("const")
            != "federation-spatial-contract/1.1"
        ):
            problems.append("contract version mismatch")

    if not isinstance(data, Mapping):
        problems.append("registry root must be an object")
        return problems
    unexpected = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unexpected:
        problems.append(f"registry contains unexpected fields: {unexpected}")
    if data.get("contract_version") != "federation-spatial-contract/1.1":
        problems.append("registry contract version mismatch")

    sources = object_rows(data, "source_manifestations", problems)
    geoms = object_rows(data, "geometry_manifestations", problems)
    entities = object_rows(data, "canonical_entities", problems)
    bindings = object_rows(data, "identity_bindings", problems)
    unresolved = object_rows(data, "unresolved", problems)

    source_ids = identifiers(sources, "manifestation_id", "source", problems)
    geom_ids = identifiers(geoms, "geometry_manifestation_id", "geometry", problems)
    entity_ids = identifiers(entities, "canonical_id", "entity", problems)
    identifiers(bindings, "binding_id", "binding", problems)

    source_set, geom_set, entity_set = set(source_ids), set(geom_ids), set(entity_ids)
    for index, source in enumerate(sources):
        if not non_empty_exact_string(source.get("source_id")):
            problems.append(
                f"source[{index}] source_id must be a non-empty exact string"
            )
        digest = source.get("byte_sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            problems.append(f"source[{index}] byte_sha256 must be a lowercase SHA-256")
        row_count = source.get("row_count")
        if row_count is not None and (
            not isinstance(row_count, int)
            or isinstance(row_count, bool)
            or row_count < 0
        ):
            problems.append(
                f"source[{index}] row_count must be a non-negative integer or null"
            )
        if not isinstance(source.get("provenance"), Mapping):
            problems.append(f"source[{index}] provenance must be an object")

    for g in geoms:
        source_id = g.get("source_manifestation_id")
        if not non_empty_exact_string(source_id) or source_id not in source_set:
            problems.append(
                f"geometry {g.get('geometry_manifestation_id')} references "
                "missing source manifestation"
            )
        if g.get("geometry") is None and g.get("geometry_status") == "PASS":
            problems.append(
                f"null geometry {g.get('geometry_manifestation_id')} cannot be PASS"
            )
        if g.get("geometry_status") not in CERTIFICATION_STATES:
            problems.append(
                f"geometry {g.get('geometry_manifestation_id')} has invalid "
                "geometry_status"
            )

    for e in entities:
        entity_id = e.get("canonical_id")
        for sid in reference_ids(
            e, "source_manifestations", f"entity {entity_id}", problems
        ):
            if sid not in source_set:
                problems.append(f"entity {entity_id} references missing source {sid}")
        for gid in reference_ids(
            e, "geometry_manifestations", f"entity {entity_id}", problems
        ):
            if gid not in geom_set:
                problems.append(f"entity {entity_id} references missing geometry {gid}")
        if e.get("identity_state") not in CERTIFICATION_STATES:
            problems.append(f"entity {entity_id} has invalid identity_state")

    for b in bindings:
        binding_id = b.get("binding_id")
        card = b.get("cardinality")
        if card not in ALLOWED_CARDINALITY:
            problems.append(f"binding {binding_id} invalid cardinality {card}")
        spatial = b.get("spatial_state")
        if spatial is not None and spatial not in ALLOWED_SPATIAL:
            problems.append(f"binding {binding_id} invalid spatial state {spatial}")
        if b.get("left_id") not in entity_set:
            problems.append(f"binding {binding_id} missing left entity")
        right = b.get("right_id")
        if right is not None and right not in entity_set:
            problems.append(f"binding {binding_id} missing right entity")
        if right is None and card not in {"0:1", "UNRESOLVED"}:
            problems.append(
                f"binding {binding_id} null right_id incompatible with {card}"
            )
        basis_values = reference_ids(
            b, "evidence_basis", f"binding {binding_id}", problems
        )
        basis = set(basis_values)
        if b.get("identity_state") == "PASS" and (
            not basis or basis <= FORBIDDEN_SOLE_IDENTITY
        ):
            problems.append(f"binding {binding_id} promotes heuristic-only identity")

    for index, row in enumerate(unresolved):
        for field in ("scope", "reason"):
            if not non_empty_exact_string(row.get(field)):
                problems.append(
                    f"unresolved[{index}] {field} must be a non-empty exact string"
                )
        if row.get("state") not in CERTIFICATION_STATES:
            problems.append(f"unresolved[{index}] has invalid state")

    if certify:
        if unresolved:
            problems.append(
                "certification requires zero unresolved residue; "
                f"found {len(unresolved)}"
            )
        if not sources or not geoms or not entities:
            problems.append(
                "certification requires non-empty source, geometry, and "
                "canonical-entity registries"
            )
        if any(
            b.get("identity_state")
            in {
                "OPEN",
                "BLOCKED",
                "PROVISIONAL",
                "CANDIDATE_NOT_IDENTITY",
                "UNRESOLVED",
            }
            for b in bindings
        ):
            problems.append("certification contains non-final identity binding state")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, default=SCHEMA)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--certify", action="store_true")
    args = parser.parse_args()

    if not args.schema.exists():
        print(f"BLOCKED: schema is absent: {args.schema}")
        return 1
    if not args.registry.exists():
        print(f"BLOCKED: canonical registry is absent: {args.registry}")
        return 1
    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        data = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print("FAIL" if args.certify else "STRUCTURAL_FAIL")
        print(f"- unable to load spatial identity documents: {exc}")
        return 1

    problems = validate_registry(data, schema, certify=args.certify)

    if problems:
        print("FAIL" if args.certify else "STRUCTURAL_FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1
    state = "CERTIFICATION_PASS" if args.certify else "STRUCTURAL_PASS"
    sources = data["source_manifestations"]
    geoms = data["geometry_manifestations"]
    entities = data["canonical_entities"]
    bindings = data["identity_bindings"]
    unresolved = data["unresolved"]
    print(
        f"{state} sources={len(sources)} geometries={len(geoms)} "
        f"entities={len(entities)} bindings={len(bindings)} "
        f"unresolved={len(unresolved)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
