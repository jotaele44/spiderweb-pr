"""Artifact-bound structural lineage admission for the opt-in benchmark.

A hashed lock is a reproducibility binding, not independent evidence that a
provider owns a geometry or that its source/derivation claims are correct.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re

from spiderweb.spatial.archipelago import (
    GeometryManifestation, GeometryDerivationState, GeometryOrigin, GeometryRepresentation,
)
from spiderweb.spatial.lineage_validation import validate_manifestation_dag
from .core import checked_bytes, digest


def _unique_pairs(pairs: list[tuple]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"DUPLICATE_JSON_FIELD:{key}")
        value[key] = item
    return value


def _invalid_constant(value: str):
    raise ValueError(f"NONFINITE_JSON_VALUE:{value}")


def admit_source_lineage(spec: dict) -> dict:
    lock = spec.get("lineage_lock")
    if not isinstance(lock, dict) or set(lock) != {"path", "sha256"}:
        raise ValueError("SOURCE_LINEAGE_LOCK_REQUIRED")
    if not isinstance(lock["path"], str) or not lock["path"]:
        raise ValueError("SOURCE_LINEAGE_LOCK_PATH_REQUIRED")
    data = checked_bytes(Path(lock["path"]), lock["sha256"])
    obj = json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
    if not isinstance(obj, dict) or set(obj) != {"schema", "nodes", "artifact_bindings"}:
        raise ValueError("INVALID_LINEAGE_LOCK_SCHEMA")
    if obj["schema"] != "spiderweb.geometry-lineage-lock.v1":
        raise ValueError("UNSUPPORTED_LINEAGE_LOCK_SCHEMA")
    if not isinstance(obj["nodes"], list) or not isinstance(obj["artifact_bindings"], list):
        raise ValueError("LINEAGE_LOCK_ARRAYS_REQUIRED")
    try:
        rows = []
        for node in obj["nodes"]:
            row = dict(node)
            row["origin"] = GeometryOrigin(row["origin"])
            row["representation"] = GeometryRepresentation(row["representation"])
            rows.append(GeometryManifestation(**row))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("INVALID_GEOMETRY_MANIFESTATION_RECORD") from exc
    dag = validate_manifestation_dag(rows)
    by_id = {row.geometry_manifestation_id: row for row in rows}
    bindings = {}
    for binding in obj["artifact_bindings"]:
        if not isinstance(binding, dict) or set(binding) != {
            "geometry_manifestation_id", "artifact_sha256", "source_snapshot_id"}:
            raise ValueError("INVALID_LINEAGE_ARTIFACT_BINDING")
        key = binding["geometry_manifestation_id"]
        if not isinstance(key, str) or key not in by_id:
            raise ValueError("ARTIFACT_BINDING_NODE_NOT_FOUND")
        if key in bindings:
            raise ValueError("DUPLICATE_LINEAGE_ARTIFACT_BINDING")
        if not isinstance(binding["artifact_sha256"], str) or not re.fullmatch(
                r"[a-f0-9]{64}", binding["artifact_sha256"]):
            raise ValueError("INVALID_LINEAGE_ARTIFACT_HASH")
        if not isinstance(binding["source_snapshot_id"], str) or not binding["source_snapshot_id"].strip():
            raise ValueError("INVALID_LINEAGE_SOURCE_SNAPSHOT")
        bindings[key] = binding
    selected = spec.get("manifestation_id")
    if not isinstance(selected, str) or selected not in bindings:
        raise ValueError("SOURCE_MANIFESTATION_NOT_BOUND")
    binding = bindings[selected]
    if binding["artifact_sha256"] != spec.get("source_sha256"):
        raise ValueError("LINEAGE_SOURCE_HASH_MISMATCH")
    if binding["source_snapshot_id"] != spec.get("source_snapshot_id"):
        raise ValueError("LINEAGE_SOURCE_SNAPSHOT_MISMATCH")
    if GeometryDerivationState(by_id[selected].derivation_state) == GeometryDerivationState.MVT:
        raise ValueError("MVT_CANNOT_BE_CANONICAL_GEOJSON_INPUT")
    return {
        "state": "PASS_STRUCTURAL_ARTIFACT_BINDING",
        "lock_sha256": digest(data), "selected_manifestation_id": selected,
        "dag": asdict(dag), "canonical_identity_certified": False,
        "source_claims_independently_verified": False,
    }
