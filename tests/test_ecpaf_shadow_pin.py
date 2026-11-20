"""Negative and positive tests for read-only Spiderweb ECPAF pin."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/afk/check_ecpaf_shadow_pin.py"
if not SCRIPT.is_file():
    SCRIPT = ROOT / "check_ecpaf_shadow_pin.py"

spec = importlib.util.spec_from_file_location("ecpaf_shadow_pin", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def synthetic_policy() -> bytes:
    p = {
        "schema_version": "ecpaf-policy/2.1",
        "policy_id": "ECPAF-V2.1",
        "policy_revision": "2.1.1",
        "authority": "jotaele44/thehub-pr",
        "mode": "SHADOW_PILOT",
        "certification": "WITHHELD",
        "independent_review_requirement": "NOT_REQUIRED",
        "advisory_review_scored": False,
        "core_repositories": ["jotaele44/spiderweb-pr"],
        "mandatory_domains": [
            "security",
            "integrity",
            "identity",
            "provenance",
            "authorization",
        ],
        "protected_operations": [
            "merge",
            "deploy",
            "release",
            "secret_write",
            "protection_change",
            "canonical_promotion",
        ],
        "protected_release_behavior": "UNCHANGED",
        "semantics": {
            "pilot_can_authorize_operations": False,
            "unknown_counts_as_pass": False,
            "missing_counts_as_pass": False,
        },
    }
    return json.dumps(p, sort_keys=True).encode()


def pin_bytes() -> bytes:
    return json.dumps(module.EXPECTED, sort_keys=True).encode()


def synthetic_verify(pin=None, policy=None, commit=None):
    raw_policy = policy if policy is not None else synthetic_policy()
    sha = hashlib.sha256(raw_policy).hexdigest()
    with mock.patch.dict(module.EXPECTED, {"policy_sha256": sha}):
        d = json.loads(pin if pin is not None else pin_bytes())
        if pin is None:
            d["policy_sha256"] = sha
        return module.verify_payload(
            json.dumps(d).encode(),
            raw_policy,
            commit if commit is not None else module.EXPECTED["authority_commit"],
        )


def test_positive_shadow_pin():
    output = synthetic_verify()
    assert output["state"] == "PASS"
    assert output["release_authorized"] is False
    assert output["certification"] == "WITHHELD"


def test_wrong_consumer_rejected():
    data = json.loads(pin_bytes())
    data["consumer_repository"] = "jotaele44/moneysweep-pr"
    with pytest.raises(module.AuthorityError):
        synthetic_verify(json.dumps(data))


def test_release_authorization_rejected():
    data = json.loads(pin_bytes())
    data["release_authorized"] = True
    with pytest.raises(module.AuthorityError):
        synthetic_verify(json.dumps(data))


def test_protected_operation_rejected():
    data = json.loads(pin_bytes())
    data["protected_operations_authorized"] = ["merge"]
    with pytest.raises(module.AuthorityError):
        synthetic_verify(json.dumps(data))


def test_mutated_commit_rejected():
    with pytest.raises(module.AuthorityError, match="commit mismatch"):
        synthetic_verify(commit="a" * 40)


def test_mutated_policy_bytes_rejected():
    with mock.patch.dict(module.EXPECTED, {"policy_sha256": "f" * 64}):
        with pytest.raises(module.AuthorityError, match="byte mismatch"):
            module.verify_payload(pin_bytes(), synthetic_policy())


def test_policy_semantics_rejected():
    data = json.loads(synthetic_policy())
    data["semantics"]["pilot_can_authorize_operations"] = True
    with pytest.raises(module.AuthorityError, match="semantics"):
        synthetic_verify(policy=json.dumps(data).encode())


def test_missing_protected_domain_rejected():
    data = json.loads(synthetic_policy())
    data["mandatory_domains"].remove("authorization")
    with pytest.raises(module.AuthorityError, match="mandatory"):
        synthetic_verify(policy=json.dumps(data).encode())


def test_independent_review_requirement_rejected():
    data = json.loads(synthetic_policy())
    data["independent_review_requirement"] = "REQUIRED"
    with pytest.raises(module.AuthorityError, match="semantics"):
        synthetic_verify(policy=json.dumps(data).encode())


def test_duplicate_key_rejected():
    with pytest.raises(module.AuthorityError, match="duplicate"):
        module.strict_json(b'{"mode":"SHADOW","mode":"RELEASE"}')


def test_nan_rejected():
    with pytest.raises(module.AuthorityError, match="invalid JSON constant"):
        module.strict_json(b'{"limit":NaN}')


def test_wrong_remote_origin_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(
            module, "git_output", return_value=b"https://example.invalid/repo"
        ):
            with pytest.raises(
                module.AuthorityError, match="unexpected authority remote"
            ):
                module.verify_git_authority(Path(tmp))


def test_invalid_authority_blob_rejected():
    with tempfile.TemporaryDirectory() as tmp:

        def fake_output(root, *args):
            if args == ("remote", "get-url", "origin"):
                return b"https://github.com/jotaele44/thehub-pr.git"
            if args[0] == "cat-file":
                return b"tree"
            raise AssertionError("unexpected Git object")

        with mock.patch.object(module, "git_output", side_effect=fake_output):
            with pytest.raises(module.AuthorityError, match="not a commit"):
                module.verify_git_authority(Path(tmp))


def test_symlink_pin_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = root / "pin.json"
        original.write_bytes(pin_bytes())
        alias = root / "alias.json"
        alias.symlink_to(original)
        with pytest.raises(module.AuthorityError, match="invalid consumer pin path"):
            module.verify_git_pin(alias, root)
