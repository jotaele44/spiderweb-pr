"""Read-only, independent-process audit of vNext materialization artifacts.

This verifier checks byte identity, row conservation, schema, Cell_ID bounds,
and reproducibility against Spiderweb's current canonical binding engine.
It is NOT an independent geodetic authority or promotion certification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from spiderweb.geographic_grid_v2 import GridV2Error, parse_cell_id
from spiderweb.grid_v2_bindings_vnext import (
    BINDING_SCHEMA_SHA256, BINDING_VERSION, GRID_MANIFEST_SHA256,
    bind_exact_geometries, binding_receipt_vnext, validate_schema_pins,
)
from spiderweb.grid_v2_source_snapshot import strict_json, verify_source_snapshot

AUDIT_CONTRACT = "pr-grid-v2-binding-artifact-audit/1.0"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = strict_json(line)
            except GridV2Error as exc:
                raise GridV2Error(f"{path}:{index}: {exc}") from exc
            if not isinstance(value, dict):
                raise GridV2Error(f"{path}:{index}: expected a JSON object")
            rows.append(value)
    except UnicodeError as exc:
        raise GridV2Error(f"invalid UTF-8 in {path}") from exc
    return rows


def _require_equal(receipt: Mapping[str, Any], key: str, expected: Any) -> None:
    if key not in receipt or type(receipt[key]) is not type(expected) or receipt[key] != expected:
        raise GridV2Error(f"binding audit mismatch: {key}")


def audit_binding_artifacts(
    *,
    input_path: Path,
    manifest_path: Path,
    bindings_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    """Audit frozen source-to-cell materialization; never promote automatically."""
    validate_schema_pins()
    paths = [Path(p).resolve(strict=True) for p in
             (input_path, manifest_path, bindings_path, receipt_path)]
    if len(set(paths)) != len(paths):
        raise GridV2Error("binding audit paths must all be distinct")
    input_path, manifest_path, bindings_path, receipt_path = paths
    source_rows = _read_jsonl(input_path)
    bindings = _read_jsonl(bindings_path)
    try:
        receipt = strict_json(receipt_path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise GridV2Error("receipt must be UTF-8") from exc
    if not isinstance(receipt, dict):
        raise GridV2Error("receipt must be a JSON object")

    source_prov = verify_source_snapshot(
        manifest_path, input_path, record_count=len(source_rows)
    )
    source_snapshot = Path(source_prov.pop("_Snapshot_Path"))
    if source_snapshot in paths:
        raise GridV2Error("source snapshot path collides with audit inputs/outputs")
    for key, value in source_prov.items():
        _require_equal(receipt, key, value)
    _require_equal(receipt, "Input_SHA256", hashlib.sha256(input_path.read_bytes()).hexdigest())
    raw_output = bindings_path.read_bytes()
    _require_equal(receipt, "Binding_Output_SHA256", hashlib.sha256(raw_output).hexdigest())
    _require_equal(receipt, "Binding_Output_Bytes", len(raw_output))
    _require_equal(receipt, "Binding_Schema_SHA256", BINDING_SCHEMA_SHA256)
    _require_equal(receipt, "Grid_Manifest_SHA256", GRID_MANIFEST_SHA256)
    _require_equal(receipt, "Contract", BINDING_VERSION)
    _require_equal(receipt, "Receipt_State", "PROVISIONAL")
    _require_equal(receipt, "Certification_State", "PROVISIONAL")
    _require_equal(receipt, "Consumer_Activation", "BLOCKED_UNTIL_CERTIFIED")

    level = receipt.get("Grid_Level")
    if level not in ("L0", "L1", "L2", "L3"):
        raise GridV2Error("missing/invalid receipt Grid_Level")
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas/pr_grid_geographic_v2_binding_vnext.schema.json"
    )
    schema = strict_json(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for index, row in enumerate(bindings, 1):
        errors = list(validator.iter_errors(row))
        if errors:
            raise GridV2Error(f"binding row {index} failed vNext JSON Schema: {errors[0].message}")
        cell = parse_cell_id(row["Cell_ID"])
        if cell.level != level or row["Grid_Level"] != level:
            raise GridV2Error(f"binding row {index} Grid_Level mismatch")
        if not row["Cell_ID"] == cell.cell_id:
            raise GridV2Error(f"noncanonical binding Cell_ID at row {index}")

    # Separate-process determinism check: all fields, row ordering, actual
    # geometry membership and complete zero-binding outcomes must reproduce.
    results = bind_exact_geometries(source_rows, level=level)
    expected = [dict(binding) for result in results for binding in result.bindings]
    if bindings != expected:
        raise GridV2Error("materialized binding rows differ from recomputed authority output")
    expected_receipt = binding_receipt_vnext(results)
    expected_receipt["Grid_Level"] = level
    for key, value in expected_receipt.items():
        _require_equal(receipt, key, value)
    _require_equal(receipt, "Input_Record_Count", len(source_rows))
    _require_equal(receipt, "Binding_Row_Count", len(bindings))
    if not all(outcome["Binding_Row_Count"] >= 0
               for outcome in receipt["Record_Outcomes"]):
        raise GridV2Error("negative record-row multiplicity")
    if sum(x["Binding_Row_Count"] for x in receipt["Record_Outcomes"]) != len(bindings):
        raise GridV2Error("record binding denominators do not close")
    return {
        "Audit_Contract": AUDIT_CONTRACT,
        "Audit_State": "PASS",
        "Certification_State": "AUDIT_ONLY",
        "Consumer_Activation": "BLOCKED_UNTIL_CERTIFIED",
        "Grid_Level": level,
        "Input_Record_Count": len(source_rows),
        "Binding_Row_Count": len(bindings),
        "Input_SHA256": receipt["Input_SHA256"],
        "Binding_Output_SHA256": receipt["Binding_Output_SHA256"],
        "Receipt_SHA256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "Source_Manifest_SHA256": source_prov["Source_Manifest_SHA256"],
        "Source_Authority_Evidence_State": "UNVERIFIED",
    }
