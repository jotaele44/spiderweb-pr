#!/usr/bin/env python3
"""Deterministic replay gate for JP_FLOOD_CERTIFICATION_V3.

This script validates only frozen, repository-local evidence. It never performs
network I/O and never changes source-state classifications.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_Q_SHA = "a1a2ccbfe0097da6f531e78f834d01be5a1555700b809d8f68b162db83d23e7a"
EXPECTED_Q_SIZE = 51_199_142
EXPECTED_FLORIDA_SHA = "cfd9695995f721be9850e4e04c415f965f66e3eb48450d234ea2d9d15eb96f83"


class GateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_scope(root: Path) -> dict[str, Any]:
    return json.loads((root / "data/jp_flood_documents/certification_v3_scope.json").read_text(encoding="utf-8"))


def load_cert(root: Path, scope: dict[str, Any]) -> dict[str, Any]:
    path = root / scope["baseline"]["certification_path"]
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    expected = scope["baseline"]["certification_sha256"]
    if digest != expected:
        raise GateError(f"CERTIFICATION_CHAIN_GATE certification bytes drifted: expected={expected} got={digest}")
    cert = json.loads(raw)
    if cert.get("certification_state") != "PASS":
        raise GateError("CERTIFICATION_CHAIN_GATE certification_state != PASS")
    return cert


def load_ledger(root: Path, scope: dict[str, Any]) -> list[dict[str, Any]]:
    path = root / scope["baseline"]["byte_ledger_path"]
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            item = dict(row)
            try:
                item["byte_size"] = int(item["byte_size"])
            except (TypeError, ValueError) as exc:
                raise GateError(f"BYTE_IDENTITY_GATE invalid byte_size for {item.get('municipality')}") from exc
            rows.append(item)
    return rows


def load_sums(root: Path, scope: dict[str, Any]) -> dict[str, str]:
    path = root / scope["baseline"]["sha256sums_path"]
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    expected = scope["baseline"]["sha256sums_sha256"]
    if digest != expected:
        raise GateError(f"CERTIFICATION_CHAIN_GATE SHA256SUMS drifted: expected={expected} got={digest}")
    sums: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        digest_value, filename = line.split("  ", 1)
        if filename in sums:
            raise GateError(f"MANIFEST_FILE_BINDING_GATE duplicate SHA256SUMS filename: {filename}")
        sums[filename] = digest_value
    return sums


def load_contract(root: Path, scope: dict[str, Any]) -> dict[str, Any]:
    return json.loads((root / scope["baseline"]["producer_contract_path"]).read_text(encoding="utf-8"))


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "municipality_denominator": len(rows),
        "series_listed": sum(r["source_state"] != "NOT_LISTED" for r in rows),
        "available": sum(r["source_state"] == "AVAILABLE" for r in rows),
        "listed_but_missing": sum(r["source_state"] == "LISTED_BUT_MISSING" for r in rows),
        "not_listed": sum(r["source_state"] == "NOT_LISTED" for r in rows),
        "operational_document_count": sum(bool(r.get("filename")) for r in rows),
        "byte_verified_count": sum(
            bool(r.get("filename"))
            and isinstance(r.get("byte_size"), int)
            and r["byte_size"] > 0
            and isinstance(r.get("sha256"), str)
            and bool(SHA256_RE.fullmatch(r["sha256"]))
            for r in rows
        ),
        "failure_count": 0,
        "total_bytes": sum(r["byte_size"] for r in rows),
    }


def _one(rows: list[dict[str, Any]], municipality: str) -> dict[str, Any]:
    matches = [r for r in rows if r["municipality"] == municipality]
    if len(matches) != 1:
        raise GateError(f"SOURCE_DENOMINATOR_GATE expected one {municipality} row, got {len(matches)}")
    return matches[0]


def validate_static(
    rows: list[dict[str, Any]],
    sums: dict[str, str],
    cert: dict[str, Any],
    contract: dict[str, Any],
    scope: dict[str, Any],
) -> dict[str, str]:
    gates: dict[str, str] = {}
    expected = scope["expected"]

    municipalities = [r["municipality"] for r in rows]
    if len(rows) != expected["municipality_denominator"] or len(set(municipalities)) != len(rows):
        raise GateError("SOURCE_DENOMINATOR_GATE municipality denominator/uniqueness mismatch")
    gates["SOURCE_DENOMINATOR_GATE"] = "PASS"

    states = Counter(r["source_state"] for r in rows)
    if set(states) - {"AVAILABLE", "LISTED_BUT_MISSING", "NOT_LISTED"}:
        raise GateError(f"SOURCE_STATE_GATE unknown states: {sorted(set(states) - {'AVAILABLE','LISTED_BUT_MISSING','NOT_LISTED'})}")
    if states["AVAILABLE"] != expected["available"] or states["LISTED_BUT_MISSING"] != expected["listed_but_missing"] or states["NOT_LISTED"] != expected["not_listed"]:
        raise GateError(f"SOURCE_STATE_GATE state arithmetic mismatch: {dict(states)}")
    gates["SOURCE_STATE_GATE"] = "PASS"

    q = _one(rows, "Quebradillas")
    f = _one(rows, "Florida")
    if q["source_state"] != "LISTED_BUT_MISSING":
        raise GateError("FALLBACK_IDENTITY_GATE Quebradillas source state changed")
    if f["source_state"] != "NOT_LISTED":
        raise GateError("FALLBACK_IDENTITY_GATE Florida source state changed")
    for row in (q, f):
        if row["operational_document_class"] != "hazard_mitigation_plan":
            raise GateError(f"FALLBACK_IDENTITY_GATE {row['municipality']} is not HMP")
        if row["fallback_relationship"] != scope["fallback_rule"]:
            raise GateError(f"FALLBACK_IDENTITY_GATE {row['municipality']} equivalence drift")
    if q["sha256"] != EXPECTED_Q_SHA or q["byte_size"] != EXPECTED_Q_SIZE:
        raise GateError("FALLBACK_IDENTITY_GATE Quebradillas frozen manifestation mismatch")
    if f["sha256"] != EXPECTED_FLORIDA_SHA:
        raise GateError("FALLBACK_IDENTITY_GATE Florida manifestation mismatch")
    for row in rows:
        if row["source_state"] == "AVAILABLE":
            if row["series_document_class"] != "flood_risk_zone_map" or row["operational_document_class"] != "flood_risk_zone_map":
                raise GateError(f"FALLBACK_IDENTITY_GATE canonical class drift for {row['municipality']}")
            if row.get("fallback_relationship"):
                raise GateError(f"FALLBACK_IDENTITY_GATE canonical row has fallback relationship: {row['municipality']}")
    gates["FALLBACK_IDENTITY_GATE"] = "PASS"

    if any(not r.get("filename") for r in rows):
        raise GateError("OPERATIONAL_COVERAGE_GATE missing operational filename")
    gates["OPERATIONAL_COVERAGE_GATE"] = "PASS"

    for row in rows:
        if row["byte_size"] <= 0 or not SHA256_RE.fullmatch(row["sha256"]):
            raise GateError(f"BYTE_IDENTITY_GATE invalid byte receipt for {row['municipality']}")
    gates["BYTE_IDENTITY_GATE"] = "PASS"

    if len(sums) != len(rows):
        raise GateError(f"BYTE_LEDGER_REPLAY_GATE SHA256SUMS count mismatch: {len(sums)} != {len(rows)}")
    for row in rows:
        if sums.get(row["filename"]) != row["sha256"]:
            raise GateError(f"BYTE_LEDGER_REPLAY_GATE filename/hash mismatch for {row['municipality']}")
    gates["BYTE_LEDGER_REPLAY_GATE"] = "PASS"

    counts = summarize(rows)
    for key, value in expected.items():
        if counts.get(key) != value:
            raise GateError(f"ARITHMETIC_CLOSURE_GATE {key}: expected={value} got={counts.get(key)}")
    if cert.get("counts") != counts:
        raise GateError("ARITHMETIC_CLOSURE_GATE certification counts do not replay from ledger")
    gates["ARITHMETIC_CLOSURE_GATE"] = "PASS"

    source_contract = contract.get("source_contract") or {}
    if contract.get("schema_version") != "jp-flood-producer-contract/1.0":
        raise GateError("CERTIFICATION_CHAIN_GATE producer contract schema drift")
    if cert.get("producer_main_sha") != contract.get("producer_merge_sha"):
        raise GateError("CERTIFICATION_CHAIN_GATE producer SHA lineage mismatch")
    if source_contract.get("municipalities") != counts["municipality_denominator"]:
        raise GateError("CERTIFICATION_CHAIN_GATE municipality lineage mismatch")
    if source_contract.get("series_available") != counts["available"]:
        raise GateError("CERTIFICATION_CHAIN_GATE available lineage mismatch")
    if source_contract.get("listed_but_missing") != counts["listed_but_missing"]:
        raise GateError("CERTIFICATION_CHAIN_GATE missing lineage mismatch")
    if source_contract.get("not_listed") != counts["not_listed"]:
        raise GateError("CERTIFICATION_CHAIN_GATE not-listed lineage mismatch")
    q_receipt = contract.get("quebradillas_receipt") or {}
    if q_receipt.get("pdf_sha256") != q["sha256"] or q_receipt.get("pdf_byte_size") != q["byte_size"]:
        raise GateError("CERTIFICATION_CHAIN_GATE Quebradillas producer receipt mismatch")
    gates["CERTIFICATION_CHAIN_GATE"] = "PASS"

    filenames = [r["filename"] for r in rows]
    if len(set(filenames)) != len(filenames):
        dupes = [name for name, count in Counter(filenames).items() if count > 1]
        raise GateError(f"MANIFEST_FILE_BINDING_GATE duplicate filenames: {dupes}")
    bindings = {(r["municipality"], r["filename"], r["byte_size"], r["sha256"]) for r in rows}
    if len(bindings) != len(rows):
        raise GateError("MANIFEST_FILE_BINDING_GATE duplicate municipality/file/byte binding")
    gates["MANIFEST_FILE_BINDING_GATE"] = "PASS"

    claim = scope.get("certified_claim")
    if claim != "78/78 operational flood-document manifestations have verified byte identity for the certified acquisition snapshot.":
        raise GateError("CERTIFICATION_SCOPE_GATE certified claim changed")
    required_nonclaims = {
        "all flood data in Puerto Rico is complete",
        "all maps are current",
        "all municipalities have canonical JP series PDFs",
        "fallback documents are methodologically equivalent to canonical series members",
        "all FEMA panels are represented",
        "all flood-risk geometry is certified",
    }
    if set(scope.get("explicit_nonclaims") or []) != required_nonclaims:
        raise GateError("CERTIFICATION_SCOPE_GATE explicit nonclaims changed")
    if scope.get("ui_semantics", {}).get("invariant") != "byte certification PASS never promotes source_state":
        raise GateError("CERTIFICATION_SCOPE_GATE source-state/UI invariant changed")
    gates["CERTIFICATION_SCOPE_GATE"] = "PASS"

    return gates


def run(root: Path) -> dict[str, Any]:
    scope = load_scope(root)
    cert = load_cert(root, scope)
    rows = load_ledger(root, scope)
    sums = load_sums(root, scope)
    contract = load_contract(root, scope)
    gates = validate_static(rows, sums, cert, contract, scope)
    result = {
        "schema_version": scope["schema_version"],
        "certification_name": scope["certification_name"],
        "gates": gates,
        "counts": summarize(rows),
        "delegated_gates": {
            "CROSS_REPO_CONTRACT_DRIFT_GATE": "aguayluz-pr",
            "SOURCE_STATE_UI_SEMANTICS_GATE": "aguayluz-pr",
            "CERTIFICATION_MUTATION_GATE": "tests/test_jp_flood_certification_v3.py",
            "REPRODUCIBLE_ACQUISITION_GATE": "live workflow",
            "SOURCE_STATE_TRANSITION_GATE": "live workflow",
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        result = run(args.root)
    except GateError as exc:
        print(f"JP_FLOOD_CERTIFICATION_V3 = FAIL: {exc}")
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    print("JP_FLOOD_CERTIFICATION_V3_STATIC = PASS")
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
