from spiderweb.subsurface.svt_contract import (
    final_public_gap_allows_negative_evidence,
    identity_basis_can_bind,
    run_state_is_terminal,
)


def test_only_pass_zero_terminal():
    assert run_state_is_terminal("PASS")
    assert run_state_is_terminal("ZERO")
    assert not run_state_is_terminal("FAIL")
    assert not run_state_is_terminal("OPEN")
    assert not run_state_is_terminal("NOT_RUN")


def test_identity_requires_hard_binding():
    assert not identity_basis_can_bind(["proximity_only"])
    assert not identity_basis_can_bind(["shared_provenance", "name_only"])
    assert identity_basis_can_bind(["stable_id"])


def test_final_public_gap_is_not_negative_evidence():
    assert final_public_gap_allows_negative_evidence() is False
