#!/usr/bin/env python3
"""Strictly read-only ECPAF authority binding for Spiderweb.

TheHub is the only cross-repo authority. This script authenticates a pinned
Git object and policy bytes, then checks Spiderweb's non-release shadow pin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PIN_RELATIVE = Path("docs/federation/ecpaf_v21_shadow_pin.json")
EXPECTED = {
    "schema": "ecpaf-shadow-consumer-pin/1",
    "consumer_repository": "jotaele44/spiderweb-pr",
    "authority_repository": "jotaele44/thehub-pr",
    "authority_commit": "5df6e4ce311d8baf9e149c6f04ce7741b8ae9ea0",
    "authority_policy_path": "governance/ecpaf/v2.1/policy.json",
    "policy_sha256": "443c8a838946b95cec31058ed3731b10102d567209cdfcc4b52968bec73f9e20",
    "policy_revision": "2.1.1",
    "execution_mode": "SHADOW_ONLY",
    "read_only": True,
    "protected_operations_authorized": [],
    "release_authorized": False,
    "certification": "WITHHELD",
}


class AuthorityError(RuntimeError):
    """Fail-closed policy pin or provenance contradiction."""


def unique_pairs(pairs):
    found = {}
    for key, value in pairs:
        if key in found:
            raise AuthorityError("duplicate JSON key: " + key)
        found[key] = value
    return found


def strict_json(raw: bytes) -> dict:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(
                AuthorityError("invalid JSON constant " + x)
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuthorityError("invalid JSON source") from exc
    if not isinstance(value, dict):
        raise AuthorityError("root JSON must be an object")
    return value


def verify_payload(
    pin_raw: bytes, policy_raw: bytes, commit: str = EXPECTED["authority_commit"]
) -> dict:
    pin = strict_json(pin_raw)
    if set(pin) != set(EXPECTED) or any(
        type(pin[key]) is not type(value) or pin[key] != value
        for key, value in EXPECTED.items()
    ):
        raise AuthorityError("consumer shadow pin mismatch")
    if commit != EXPECTED["authority_commit"]:
        raise AuthorityError("authority commit mismatch")
    digest = hashlib.sha256(policy_raw).hexdigest()
    if digest != EXPECTED["policy_sha256"]:
        raise AuthorityError("authority policy byte mismatch")
    policy = strict_json(policy_raw)
    if (
        policy.get("schema_version") != "ecpaf-policy/2.1"
        or policy.get("policy_id") != "ECPAF-V2.1"
        or policy.get("policy_revision") != "2.1.1"
        or policy.get("authority") != EXPECTED["authority_repository"]
        or policy.get("mode") != "SHADOW_PILOT"
        or policy.get("certification") != "WITHHELD"
        or policy.get("independent_review_requirement") != "NOT_REQUIRED"
        or policy.get("advisory_review_scored") is not False
        or "jotaele44/spiderweb-pr" not in policy.get("core_repositories", [])
    ):
        raise AuthorityError("authority policy semantics mismatch")
    if set(policy.get("mandatory_domains", [])) != {
        "security",
        "integrity",
        "identity",
        "provenance",
        "authorization",
    }:
        raise AuthorityError("mandatory governance domains mismatch")
    if not {
        "merge",
        "deploy",
        "release",
        "secret_write",
        "protection_change",
        "canonical_promotion",
    }.issubset(set(policy.get("protected_operations", []))):
        raise AuthorityError("protected operations mismatch")
    if (
        policy.get("protected_release_behavior") != "UNCHANGED"
        or policy.get("semantics", {}).get("pilot_can_authorize_operations")
        is not False
        or policy.get("semantics", {}).get("unknown_counts_as_pass") is not False
        or policy.get("semantics", {}).get("missing_counts_as_pass") is not False
    ):
        raise AuthorityError("fail-closed policy semantics mismatch")
    return {
        "state": "PASS",
        "consumer": pin["consumer_repository"],
        "authority_commit": commit,
        "policy_sha256": digest,
        "policy_revision": pin["policy_revision"],
        "release_authorized": False,
        "certification": "WITHHELD",
    }


def git_output(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise AuthorityError("authority Git verification failed: " + " ".join(args[:2]))
    return result.stdout.strip() if args[0] != "show" else result.stdout


def verify_git_authority(root: Path) -> bytes:
    if not root.is_dir() or root.is_symlink():
        raise AuthorityError("missing authoritative Git repository")
    origin = git_output(root, "remote", "get-url", "origin").decode()
    if not re.fullmatch(
        r"(?:https://github\.com/jotaele44/thehub-pr(?:\.git)?|git@github\.com:jotaele44/thehub-pr(?:\.git)?)",
        origin,
    ):
        raise AuthorityError("unexpected authority remote origin")
    kind = git_output(root, "cat-file", "-t", EXPECTED["authority_commit"]).decode()
    if kind != "commit":
        raise AuthorityError("authority object is not a commit")
    object_path = EXPECTED["authority_commit"] + ":" + EXPECTED["authority_policy_path"]
    return git_output(root, "show", object_path)


def verify_git_pin(pin: Path, authority_repo: Path) -> dict:
    if not pin.is_file() or pin.is_symlink():
        raise AuthorityError("invalid consumer pin path")
    policy_raw = verify_git_authority(authority_repo)
    return verify_payload(pin.read_bytes(), policy_raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", type=Path, default=PIN_RELATIVE)
    parser.add_argument("--thehub-checkout", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_git_pin(args.pin, args.thehub_checkout)
    except AuthorityError as exc:
        print(
            json.dumps({"state": "INTEGRITY_BLOCKED", "error": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
