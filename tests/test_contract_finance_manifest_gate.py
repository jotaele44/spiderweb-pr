from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from readiness.contract_finance_manifest_gate import (
    ContractFinanceManifestGateError,
    assess_contract_finance_manifest,
    validate_contract_finance_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "contract_finance_artifact_manifest.json"


def _manifest() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "artifact_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_valid_manifest_passes_gate():
    report = validate_contract_finance_manifest(FIXTURE)

    assert report["status"] == "READY"
    assert report["producer_repository"] == "jotaele44/Contract-Sweeper"
    assert report["artifact_count"] == 11
    assert "outputs/contract_finance/contract_finance_geo_rows.csv" in report["declared_paths"]


def test_manifest_assessment_reports_blocked_without_raising(tmp_path):
    payload = _manifest()
    payload["validation"]["readiness_passed"] = False
    path = _write(tmp_path, payload)

    report = assess_contract_finance_manifest(path)

    assert report["status"] == "BLOCKED"
    assert any("readiness_passed" in error for error in report["errors"])


def test_manifest_rejects_wrong_type(tmp_path):
    payload = _manifest()
    payload["manifest_type"] = "wrong_manifest"
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="manifest_type"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_wrong_producer(tmp_path):
    payload = _manifest()
    payload["producer"]["repository"] = "other/repo"
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="producer.repository"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_missing_producer_commit(tmp_path):
    payload = _manifest()
    payload["producer"]["commit"] = ""
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="producer.commit"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_missing_required_artifact(tmp_path):
    payload = _manifest()
    payload["artifacts"] = [
        artifact for artifact in payload["artifacts"]
        if artifact["path"] != "outputs/contract_finance/entity_graph.graphml"
    ]
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="missing required artifacts"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_artifact_without_blob_sha(tmp_path):
    payload = _manifest()
    payload["artifacts"][0] = copy.deepcopy(payload["artifacts"][0])
    payload["artifacts"][0]["git_blob_sha"] = ""
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="missing git_blob_sha"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_aggregate_as_source_of_truth(tmp_path):
    payload = _manifest()
    payload["consumer_contract"]["row_level_source_of_truth"] = "outputs/contract_finance/municipality_funding_density.csv"
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="row_level_source_of_truth"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_unexplained_unknown_rows(tmp_path):
    payload = _manifest()
    payload["validation"]["unknown_has_unclassified"] = True
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="unknown_has_unclassified"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_missing_graph_lineage(tmp_path):
    payload = _manifest()
    payload["validation"]["graph_edges_missing_lineage"] = 1
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="lineage"):
        validate_contract_finance_manifest(path)


def test_manifest_rejects_unreconciled_totals(tmp_path):
    payload = _manifest()
    payload["validation"]["density_total_amount"] = 1.0
    path = _write(tmp_path, payload)

    with pytest.raises(ContractFinanceManifestGateError, match="total amounts"):
        validate_contract_finance_manifest(path)
