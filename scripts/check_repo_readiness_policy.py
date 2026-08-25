#!/usr/bin/env python3
"""Validate the Spiderweb repository-readiness policy and audit reports.

This gate validates claim integrity, not product readiness. A truthful FAIL/OPEN
report is valid input; the gate fails when a report claims CERTIFIED without
all mandatory domains at PASS and zero mandatory unresolved residue.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class PolicyError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{path} must contain a JSON object")
    return value


def require_unique_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise PolicyError(f"{field} must be a non-empty list of strings")
    if len(value) != len(set(value)):
        raise PolicyError(f"{field} contains duplicates")
    return value


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema") != "prii.repo-readiness-policy/v1":
        raise PolicyError("unsupported policy schema")

    mandatory = require_unique_strings(policy.get("mandatory_domains"), "mandatory_domains")
    states = set(require_unique_strings(policy.get("domain_states"), "domain_states"))
    evidence = set(require_unique_strings(policy.get("evidence_classes"), "evidence_classes"))
    closure = require_unique_strings(policy.get("capability_closure_chain"), "capability_closure_chain")
    forbidden = set(require_unique_strings(policy.get("identity_forbidden_as_sole_evidence"), "identity_forbidden_as_sole_evidence"))
    adversarial = set(require_unique_strings(policy.get("required_adversarial_cases"), "required_adversarial_cases"))

    required_states = {"PASS", "FAIL", "OPEN", "BLOCKED", "PROVISIONAL", "UNRESOLVED", "SUPERSEDED"}
    if not required_states <= states:
        raise PolicyError(f"domain_states missing {sorted(required_states - states)}")

    required_evidence = {"FACT", "COMPUTED", "BINDING", "INFERENCE", "ASSUMPTION", "HYPOTHESIS", "UNKNOWN"}
    if evidence != required_evidence:
        raise PolicyError("evidence_classes must exactly preserve the seven evidence classes")

    required_closure = ["user_intent", "gui_action", "handler", "service", "data_source", "artifact", "validation", "user_feedback"]
    if closure != required_closure:
        raise PolicyError("capability_closure_chain changed ordering or membership")

    required_forbidden = {"NAME_ONLY", "NORMALIZED_NAME_ONLY", "COUNT_EQUALITY", "NEAREST_ONLY", "PROXIMITY_ONLY", "SAME_CATEGORY", "SOURCE_ABSENCE"}
    if not required_forbidden <= forbidden:
        raise PolicyError(f"identity safeguards missing {sorted(required_forbidden - forbidden)}")

    required_adversarial = {"NULL", "TIE", "DUPLICATE", "M:N", "SCHEMA_DRIFT", "NETWORK_FAILURE"}
    if not required_adversarial <= adversarial:
        raise PolicyError(f"adversarial denominator missing {sorted(required_adversarial - adversarial)}")

    rule = policy.get("certification_rule")
    if not isinstance(rule, dict):
        raise PolicyError("certification_rule must be an object")
    if rule.get("certified_state") != "CERTIFIED":
        raise PolicyError("certified_state must remain CERTIFIED")
    if rule.get("required_domain_state") != "PASS":
        raise PolicyError("required_domain_state must remain PASS")
    if rule.get("max_unresolved_mandatory_residue") != 0:
        raise PolicyError("certification must require zero unresolved mandatory residue")
    if rule.get("script_success_is_certification") is not False:
        raise PolicyError("script success must never equal certification")

    invariants = policy.get("invariants")
    if not isinstance(invariants, dict) or not all(invariants.get(key) is True for key in (
        "preserve_passed_artifacts",
        "freeze_before_observation",
        "full_candidate_sets_preserved",
        "ties_fail_closed",
        "unexpected_many_to_many_fails_closed",
        "arithmetic_must_close",
        "mutable_sources_are_versioned_snapshots",
    )):
        raise PolicyError("one or more fail-closed invariants were removed")

    if len(mandatory) < 10:
        raise PolicyError("mandatory domain denominator is unexpectedly small")


def validate_report(policy: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != "prii.repo-readiness-report/v1":
        raise PolicyError("unsupported report schema")

    snapshot = report.get("snapshot")
    if not isinstance(snapshot, dict):
        raise PolicyError("report snapshot must be an object")
    for field in ("commit_sha", "tree_sha"):
        value = snapshot.get(field)
        if not isinstance(value, str) or not SHA40_RE.fullmatch(value):
            raise PolicyError(f"snapshot.{field} must be a lowercase 40-character git SHA")
    for field in ("branches_total_at_freeze", "open_prs_at_freeze", "open_issues_at_freeze"):
        value = snapshot.get(field)
        if not isinstance(value, int) or value < 0:
            raise PolicyError(f"snapshot.{field} must be a non-negative integer")

    allowed_states = set(policy["domain_states"])
    allowed_evidence = set(policy["evidence_classes"])
    domains = report.get("domains")
    if not isinstance(domains, dict):
        raise PolicyError("report domains must be an object")

    missing = [name for name in policy["mandatory_domains"] if name not in domains]
    if missing:
        raise PolicyError(f"report is missing mandatory domains: {missing}")

    unresolved_total = 0
    non_pass: list[str] = []
    for name in policy["mandatory_domains"]:
        entry = domains[name]
        if not isinstance(entry, dict):
            raise PolicyError(f"domain {name} must be an object")
        state = entry.get("state")
        if state not in allowed_states:
            raise PolicyError(f"domain {name} has invalid state {state!r}")
        evidence_class = entry.get("evidence_class")
        if evidence_class not in allowed_evidence:
            raise PolicyError(f"domain {name} has invalid evidence class {evidence_class!r}")
        residue = entry.get("mandatory_unresolved_residue")
        if not isinstance(residue, int) or residue < 0:
            raise PolicyError(f"domain {name} unresolved residue must be a non-negative integer")
        unresolved_total += residue
        if state != policy["certification_rule"]["required_domain_state"]:
            non_pass.append(name)

    certification_state = report.get("certification_state")
    if not isinstance(certification_state, str) or not certification_state:
        raise PolicyError("certification_state must be a non-empty string")

    if certification_state == policy["certification_rule"]["certified_state"]:
        if non_pass:
            raise PolicyError(f"false certification: mandatory domains not PASS: {non_pass}")
        if unresolved_total != 0:
            raise PolicyError(f"false certification: mandatory unresolved residue is {unresolved_total}, expected 0")

    return {
        "certification_state": certification_state,
        "mandatory_domains": len(policy["mandatory_domains"]),
        "non_pass_domains": non_pass,
        "mandatory_unresolved_residue": unresolved_total,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=Path(".federation/repo-readiness-policy.json"))
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        policy = load_json(args.policy)
        validate_policy(policy)
        summary: dict[str, Any] = {"policy": "PASS"}
        if args.report is not None:
            report = load_json(args.report)
            summary["report"] = validate_report(policy, report)
    except PolicyError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
