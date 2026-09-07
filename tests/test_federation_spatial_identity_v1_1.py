import importlib.util
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_federation_spatial_identity_v1_1.py"
SCHEMA = ROOT / "schemas" / "federation_spatial_identity_v1_1.schema.json"
REGISTRY = ROOT / "registry" / "spatial" / "federation_spatial_identity_v1_1.json"
spec = importlib.util.spec_from_file_location("spatial_identity_validator", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def documents():
    return (
        json.loads(REGISTRY.read_text(encoding="utf-8")),
        json.loads(SCHEMA.read_text(encoding="utf-8")),
    )


def test_current_registry_passes_structural_validation_only():
    registry, schema = documents()
    assert module.validate_registry(registry, schema) == []
    certification = module.validate_registry(registry, schema, certify=True)
    assert any("zero unresolved residue" in problem for problem in certification)


def test_non_array_collection_fails_closed():
    registry, schema = documents()
    registry["source_manifestations"] = {}
    problems = module.validate_registry(registry, schema)
    assert "source_manifestations must be an array" in problems


def test_missing_and_whitespace_ids_fail_without_normalization():
    registry, schema = documents()
    mutated = deepcopy(registry)
    mutated["source_manifestations"][0]["manifestation_id"] = " source-1 "
    problems = module.validate_registry(mutated, schema)
    assert any(
        "manifestation_id must be a non-empty exact string" in problem
        for problem in problems
    )


def test_string_evidence_basis_does_not_iterate_as_characters():
    registry, schema = documents()
    mutated = deepcopy(registry)
    mutated["canonical_entities"] = [
        {
            "canonical_id": "entity-1",
            "entity_type": "place",
            "canonical_name": "Place",
            "identity_state": "PROVISIONAL",
            "source_manifestations": [],
            "geometry_manifestations": [],
        }
    ]
    mutated["identity_bindings"] = [
        {
            "binding_id": "binding-1",
            "left_id": "entity-1",
            "right_id": None,
            "cardinality": "0:1",
            "evidence_basis": "NAME_ONLY",
            "evidence_state": "INFERENCE",
            "identity_state": "CANDIDATE_NOT_IDENTITY",
        }
    ]
    problems = module.validate_registry(mutated, schema)
    assert any("evidence_basis must be an array" in problem for problem in problems)
