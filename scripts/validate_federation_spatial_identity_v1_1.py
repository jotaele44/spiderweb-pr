#!/usr/bin/env python3
"""Fail-closed structural/invariant validator for federation-spatial-contract/1.1."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/federation_spatial_identity_v1_1.schema.json"
REGISTRY = ROOT / "registry/spatial/federation_spatial_identity_v1_1.json"
ALLOWED_CARDINALITY = {"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"}
ALLOWED_SPATIAL = {"FULLY_WITHIN", "PARTIAL", "TOUCH_ONLY", "OUTSIDE", "NULL_EMPTY", "UNRESOLVED"}
FORBIDDEN_SOLE_IDENTITY = {"NAME_ONLY", "NORMALIZED_NAME_ONLY", "COUNT_EQUALITY", "NEAREST_ONLY", "PROXIMITY_ONLY", "SAME_CATEGORY", "SOURCE_ABSENCE"}
ACCEPTED_IDENTITY = {"PASS"}


def duplicates(values):
    seen, dup = set(), set()
    for value in values:
        if value in seen:
            dup.add(value)
        seen.add(value)
    return sorted(dup)


def main() -> int:
    problems = []
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if schema.get("$id") != "https://federation.local/schemas/federation_spatial_identity_v1_1.schema.json":
        problems.append("schema $id mismatch")
    if schema.get("properties", {}).get("contract_version", {}).get("const") != "federation-spatial-contract/1.1":
        problems.append("contract version mismatch")

    if not REGISTRY.exists():
        print("OPEN: registry not yet instantiated; schema gate PASS, data gate OPEN")
        return 2 if problems else 0

    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if data.get("contract_version") != "federation-spatial-contract/1.1":
        problems.append("registry contract version mismatch")

    sources = data.get("source_manifestations", [])
    geoms = data.get("geometry_manifestations", [])
    entities = data.get("canonical_entities", [])
    bindings = data.get("identity_bindings", [])
    unresolved = data.get("unresolved", [])

    source_ids = [r.get("manifestation_id") for r in sources]
    geom_ids = [r.get("geometry_manifestation_id") for r in geoms]
    entity_ids = [r.get("canonical_id") for r in entities]
    binding_ids = [r.get("binding_id") for r in bindings]
    for label, vals in (("source", source_ids), ("geometry", geom_ids), ("entity", entity_ids), ("binding", binding_ids)):
        d = duplicates(vals)
        if d:
            problems.append(f"duplicate {label} ids: {d}")

    source_set, geom_set, entity_set = set(source_ids), set(geom_ids), set(entity_ids)
    for g in geoms:
        if g.get("source_manifestation_id") not in source_set:
            problems.append(f"geometry {g.get('geometry_manifestation_id')} references missing source manifestation")
        if g.get("geometry") is None and g.get("geometry_status") == "PASS":
            problems.append(f"null geometry {g.get('geometry_manifestation_id')} cannot be PASS")

    for e in entities:
        for sid in e.get("source_manifestations", []):
            if sid not in source_set:
                problems.append(f"entity {e.get('canonical_id')} references missing source {sid}")
        for gid in e.get("geometry_manifestations", []):
            if gid not in geom_set:
                problems.append(f"entity {e.get('canonical_id')} references missing geometry {gid}")

    for b in bindings:
        card = b.get("cardinality")
        if card not in ALLOWED_CARDINALITY:
            problems.append(f"binding {b.get('binding_id')} invalid cardinality {card}")
        spatial = b.get("spatial_state")
        if spatial is not None and spatial not in ALLOWED_SPATIAL:
            problems.append(f"binding {b.get('binding_id')} invalid spatial state {spatial}")
        if b.get("left_id") not in entity_set:
            problems.append(f"binding {b.get('binding_id')} missing left entity")
        right = b.get("right_id")
        if right is not None and right not in entity_set:
            problems.append(f"binding {b.get('binding_id')} missing right entity")
        if right is None and card not in {"0:1", "UNRESOLVED"}:
            problems.append(f"binding {b.get('binding_id')} null right_id incompatible with {card}")
        basis = set(b.get("evidence_basis", []))
        if b.get("identity_state") in ACCEPTED_IDENTITY and basis and basis <= FORBIDDEN_SOLE_IDENTITY:
            problems.append(f"binding {b.get('binding_id')} promotes heuristic-only identity")

    for i, row in enumerate(unresolved):
        if not row.get("reason"):
            problems.append(f"unresolved[{i}] missing reason")

    if problems:
        print("FAIL")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"PASS sources={len(sources)} geometries={len(geoms)} entities={len(entities)} bindings={len(bindings)} unresolved={len(unresolved)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
