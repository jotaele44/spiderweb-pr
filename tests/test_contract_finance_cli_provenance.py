from __future__ import annotations

from scripts.build_contract_finance_layer import main


def test_artifact_manifest_requires_expected_producer_commit(tmp_path):
    assert main([
        "--input",
        str(tmp_path),
        "--artifact-manifest",
        str(tmp_path / "artifact_manifest.json"),
    ]) == 2


def test_expected_producer_commit_requires_artifact_manifest(tmp_path):
    assert main([
        "--input",
        str(tmp_path),
        "--expected-producer-commit",
        "0" * 40,
    ]) == 2
