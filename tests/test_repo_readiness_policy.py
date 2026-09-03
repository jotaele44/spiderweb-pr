from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.check_repo_readiness_policy import (
    PolicyError,
    load_json,
    validate_policy,
    validate_report,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / ".federation" / "repo-readiness-policy.json"
REPORT_PATH = ROOT / "audit" / "repo_readiness" / "2026-08-24.json"


def _inputs():
    policy = load_json(POLICY_PATH)
    report = load_json(REPORT_PATH)
    return policy, report


def test_policy_and_truthful_fail_snapshot_are_valid():
    policy, report = _inputs()
    validate_policy(policy)
    summary = validate_report(policy, report)
    assert summary["certification_state"] == "FAIL"
    assert summary["mandatory_unresolved_residue"] > 0
    assert "ux" in summary["non_pass_domains"]


def test_false_certification_with_open_domain_fails_closed():
    policy, report = _inputs()
    report = copy.deepcopy(report)
    report["certification_state"] = "CERTIFIED"
    with pytest.raises(PolicyError, match="false certification"):
        validate_report(policy, report)


def test_false_certification_with_hidden_residue_fails_closed():
    policy, report = _inputs()
    report = copy.deepcopy(report)
    for entry in report["domains"].values():
        entry["state"] = "PASS"
        entry["mandatory_unresolved_residue"] = 0
    report["domains"]["testing"]["mandatory_unresolved_residue"] = 1
    report["certification_state"] = "CERTIFIED"
    with pytest.raises(PolicyError, match="unresolved residue"):
        validate_report(policy, report)


@pytest.mark.parametrize(
    "state",
    [
        "CERTIFIED ",
        " CERTIFIED",
        "certified",
        "CERTIFIED\n",
        "PASS ",
        "READY",
    ],
)
def test_malformed_or_unknown_certification_state_fails_closed(state):
    policy, report = _inputs()
    report = copy.deepcopy(report)
    report["certification_state"] = state
    with pytest.raises(PolicyError, match="invalid certification_state"):
        validate_report(policy, report)


def test_allowed_noncertified_states_remain_truthful():
    policy, report = _inputs()
    for state in policy["domain_states"]:
        candidate = copy.deepcopy(report)
        candidate["certification_state"] = state
        assert validate_report(policy, candidate)["certification_state"] == state


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("snapshot", "open_prs_at_freeze"), True),
        (("domains", "testing", "mandatory_unresolved_residue"), False),
    ],
)
def test_boolean_counts_fail_closed(path, value):
    policy, report = _inputs()
    report = copy.deepcopy(report)
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(PolicyError, match="non-negative integer"):
        validate_report(policy, report)


def test_missing_mandatory_domain_fails_closed():
    policy, report = _inputs()
    report = copy.deepcopy(report)
    del report["domains"]["security"]
    with pytest.raises(PolicyError, match="missing mandatory domains"):
        validate_report(policy, report)


def test_identity_safeguard_removal_is_rejected():
    policy, _ = _inputs()
    policy = copy.deepcopy(policy)
    policy["identity_forbidden_as_sole_evidence"].remove("PROXIMITY_ONLY")
    with pytest.raises(PolicyError, match="identity safeguards missing"):
        validate_policy(policy)


def test_adversarial_denominator_removal_is_rejected():
    policy, _ = _inputs()
    policy = copy.deepcopy(policy)
    policy["required_adversarial_cases"].remove("M:N")
    with pytest.raises(PolicyError, match="adversarial denominator missing"):
        validate_policy(policy)


def test_policy_state_with_surrounding_whitespace_is_rejected():
    policy, _ = _inputs()
    policy = copy.deepcopy(policy)
    policy["domain_states"].append("CERTIFIED ")
    with pytest.raises(PolicyError, match="non-empty list of strings"):
        validate_policy(policy)
