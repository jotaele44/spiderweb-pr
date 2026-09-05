import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_federation_spatial_migration_receipt_v1_1.py"
spec = importlib.util.spec_from_file_location("spatial_migration_receipt", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def receipt(**overrides):
    row = {
        "contract_version": "federation-spatial-migration/1.1",
        "migration_id": "m1",
        "producer_repo": "aguayluz-pr",
        "source_count": 10,
        "retained_count": 8,
        "excluded_count": 1,
        "unresolved_count": 1,
        "join_output_count": 8,
        "declared_cardinality": "1:1",
        "multiplication_expected": False,
        "multiplication_reason": None,
        "provenance": {},
    }
    row.update(overrides)
    return row


def test_exact_arithmetic_closure_passes():
    assert module.validate(receipt()) == []


def test_source_arithmetic_mismatch_fails():
    problems = module.validate(receipt(source_count=11))
    assert any("arithmetic closure failed" in problem for problem in problems)


def test_one_to_one_multiplication_fails():
    problems = module.validate(receipt(join_output_count=9))
    assert any("unexpected join multiplication" in problem for problem in problems)


def test_one_to_many_requires_explicit_multiplication_receipt():
    problems = module.validate(receipt(declared_cardinality="1:N", join_output_count=12))
    assert any("multiplication not declared" in problem for problem in problems)


def test_one_to_many_explicit_multiplication_passes():
    problems = module.validate(
        receipt(
            declared_cardinality="1:N",
            join_output_count=12,
            multiplication_expected=True,
            multiplication_reason="one source asset binds to multiple historical geometry manifestations",
        )
    )
    assert problems == []


def test_retained_rows_cannot_vanish():
    problems = module.validate(receipt(join_output_count=0))
    assert any("retained rows vanished" in problem for problem in problems)


def test_unresolved_cardinality_requires_unresolved_rows():
    problems = module.validate(
        receipt(
            source_count=8,
            retained_count=8,
            excluded_count=0,
            unresolved_count=0,
            join_output_count=8,
            declared_cardinality="UNRESOLVED",
        )
    )
    assert any("requires unresolved_count" in problem for problem in problems)
