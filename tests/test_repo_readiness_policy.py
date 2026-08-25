from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.check_repo_readiness_policy import PolicyError, load_json, validate_policy, validate_report

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
