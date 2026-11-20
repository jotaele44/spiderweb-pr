from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_jp_flood_certification_v3.py"
spec = importlib.util.spec_from_file_location("jp_flood_v3", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _fixture():
    scope = mod.load_scope(ROOT)
    cert = mod.load_cert(ROOT, scope)
    rows = mod.load_ledger(ROOT, scope)
    sums = mod.load_sums(ROOT, scope)
    contract = mod.load_contract(ROOT, scope)
    return scope, cert, rows, sums, contract


def _validate(rows=None, sums=None, cert=None, contract=None, scope=None):
    base_scope, base_cert, base_rows, base_sums, base_contract = _fixture()
    return mod.validate_static(
        rows if rows is not None else base_rows,
        sums if sums is not None else base_sums,
        cert if cert is not None else base_cert,
        contract if contract is not None else base_contract,
        scope if scope is not None else base_scope,
    )


def test_v3_frozen_snapshot_passes() -> None:
    result = mod.run(ROOT)
    assert result["counts"]["municipality_denominator"] == 78
    assert result["counts"]["byte_verified_count"] == 78
    assert result["counts"]["failure_count"] == 0
    assert result["gates"]["CERTIFICATION_SCOPE_GATE"] == "PASS"


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda rows: rows.__setitem__(0, {**rows[0], "sha256": "0" * 64}), "BYTE_LEDGER_REPLAY_GATE"),
        (lambda rows: rows.__setitem__(0, {**rows[0], "byte_size": rows[0]["byte_size"] + 1}), "ARITHMETIC_CLOSURE_GATE"),
        (lambda rows: rows.append(copy.deepcopy(rows[0])), "SOURCE_DENOMINATOR_GATE"),
        (lambda rows: rows.pop(), "SOURCE_DENOMINATOR_GATE"),
    ],
)
def test_ledger_mutations_fail_closed(mutator, match) -> None:
    _, _, rows, _, _ = _fixture()
    rows = copy.deepcopy(rows)
    mutator(rows)
    with pytest.raises(mod.GateError, match=match):
        _validate(rows=rows)


def test_quebradillas_promotion_fails_closed() -> None:
    _, _, rows, _, _ = _fixture()
    rows = copy.deepcopy(rows)
    q = next(r for r in rows if r["municipality"] == "Quebradillas")
    q["source_state"] = "AVAILABLE"
    with pytest.raises(mod.GateError, match="SOURCE_STATE_GATE|FALLBACK_IDENTITY_GATE"):
        _validate(rows=rows)


def test_florida_promotion_fails_closed() -> None:
    _, _, rows, _, _ = _fixture()
    rows = copy.deepcopy(rows)
    f = next(r for r in rows if r["municipality"] == "Florida")
    f["source_state"] = "AVAILABLE"
    with pytest.raises(mod.GateError, match="SOURCE_STATE_GATE|FALLBACK_IDENTITY_GATE"):
        _validate(rows=rows)


def test_fallback_equivalence_promotion_fails_closed() -> None:
    _, _, rows, _, _ = _fixture()
    rows = copy.deepcopy(rows)
    q = next(r for r in rows if r["municipality"] == "Quebradillas")
    q["fallback_relationship"] = "equivalent_series_member"
    with pytest.raises(mod.GateError, match="FALLBACK_IDENTITY_GATE"):
        _validate(rows=rows)


def test_fallback_hash_substitution_fails_closed() -> None:
    _, _, rows, _, _ = _fixture()
    rows = copy.deepcopy(rows)
    q = next(r for r in rows if r["municipality"] == "Quebradillas")
    f = next(r for r in rows if r["municipality"] == "Florida")
    q["sha256"] = f["sha256"]
    with pytest.raises(mod.GateError, match="FALLBACK_IDENTITY_GATE"):
        _validate(rows=rows)


def test_certification_count_tampering_fails_closed() -> None:
    _, cert, _, _, _ = _fixture()
    cert = copy.deepcopy(cert)
    cert["counts"]["total_bytes"] += 1
    with pytest.raises(mod.GateError, match="ARITHMETIC_CLOSURE_GATE"):
        _validate(cert=cert)


def test_producer_sha_lineage_tampering_fails_closed() -> None:
    _, _, _, _, contract = _fixture()
    contract = copy.deepcopy(contract)
    contract["producer_merge_sha"] = "0" * 40
    with pytest.raises(mod.GateError, match="CERTIFICATION_CHAIN_GATE"):
        _validate(contract=contract)


def test_filename_swap_fails_closed() -> None:
    _, _, rows, _, _ = _fixture()
    rows = copy.deepcopy(rows)
    rows[0]["filename"], rows[1]["filename"] = rows[1]["filename"], rows[0]["filename"]
    with pytest.raises(mod.GateError, match="BYTE_LEDGER_REPLAY_GATE"):
        _validate(rows=rows)


def test_scope_expansion_fails_closed() -> None:
    scope, _, _, _, _ = _fixture()
    scope = copy.deepcopy(scope)
    scope["certified_claim"] = "All Puerto Rico flood data is complete."
    with pytest.raises(mod.GateError, match="CERTIFICATION_SCOPE_GATE"):
        _validate(scope=scope)
