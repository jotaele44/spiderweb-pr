from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_MANIFEST_TYPE = "contract_finance_artifact_manifest"
EXPECTED_PRODUCER_REPO = "jotaele44/Contract-Sweeper"
EXPECTED_ROW_LEVEL_SOURCE = "outputs/contract_finance/contract_finance_geo_rows.csv"
EXPECTED_READINESS_GATE = "outputs/contract_finance/spiderweb_engine_readiness_reassessment.json"
EXPECTED_REQUIRED_ARTIFACT_COUNT = 11

REQUIRED_ARTIFACTS = {
    "outputs/contract_finance/contract_finance_geo_rows.csv",
    "outputs/contract_finance/municipality_funding_density.csv",
    "outputs/contract_finance/unknown_decomposition.csv",
    "outputs/contract_finance/unknown_decomposition_summary.json",
    "outputs/contract_finance/san_juan_hq_bias_report.csv",
    "outputs/contract_finance/san_juan_hq_bias_summary.json",
    "outputs/contract_finance/entity_graph.graphml",
    "outputs/contract_finance/entity_graph_edge_metadata_audit.csv",
    "outputs/contract_finance/entity_graph_qa_report.json",
    "outputs/contract_finance/spiderweb_engine_readiness_reassessment.json",
    "data/reference/pr_78_municipio_crosswalk.csv",
}

REQUIRED_ARTIFACT_FIELDS = {"path", "required", "format", "role", "git_blob_sha"}


class ContractFinanceManifestGateError(ValueError):
    """Raised when the Contract-Sweeper contract-finance manifest is unsafe to consume."""


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractFinanceManifestGateError(f"manifest missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractFinanceManifestGateError(f"manifest invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ContractFinanceManifestGateError("manifest must be a JSON object")
    return payload


def assess_contract_finance_manifest(manifest_path: str | Path) -> dict[str, Any]:
    manifest = _load_manifest(Path(manifest_path))
    errors: list[str] = []

    if manifest.get("manifest_type") != EXPECTED_MANIFEST_TYPE:
        errors.append("manifest_type must be contract_finance_artifact_manifest")

    producer = manifest.get("producer")
    if not isinstance(producer, dict):
        errors.append("producer must be an object")
        producer = {}

    if producer.get("repository") != EXPECTED_PRODUCER_REPO:
        errors.append("producer.repository must be jotaele44/Contract-Sweeper")
    if not producer.get("commit"):
        errors.append("producer.commit is required")

    consumer_contract = manifest.get("consumer_contract")
    if not isinstance(consumer_contract, dict):
        errors.append("consumer_contract must be an object")
        consumer_contract = {}

    if consumer_contract.get("consume_declared_outputs_only") is not True:
        errors.append("consumer_contract.consume_declared_outputs_only must be true")
    if consumer_contract.get("do_not_consume_aggregate_municipality_csv_as_source_of_truth") is not True:
        errors.append("aggregate municipality CSV must be marked non-source-of-truth")
    if consumer_contract.get("row_level_source_of_truth") != EXPECTED_ROW_LEVEL_SOURCE:
        errors.append("row_level_source_of_truth must be contract_finance_geo_rows.csv")
    if consumer_contract.get("readiness_gate") != EXPECTED_READINESS_GATE:
        errors.append("readiness_gate must point to spiderweb_engine_readiness_reassessment.json")
    if consumer_contract.get("graph_edge_metadata_required") is not True:
        errors.append("graph_edge_metadata_required must be true")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
        artifacts = []

    declared_paths = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"artifact[{index}] must be an object")
            continue
        missing_fields = REQUIRED_ARTIFACT_FIELDS - set(artifact)
        if missing_fields:
            errors.append(f"artifact[{index}] missing fields: {sorted(missing_fields)}")
        path = artifact.get("path")
        if isinstance(path, str):
            declared_paths.add(path)
        if artifact.get("required") is not True:
            errors.append(f"artifact[{index}] must be required=true")
        if not artifact.get("git_blob_sha"):
            errors.append(f"artifact[{index}] missing git_blob_sha")

    missing_artifacts = REQUIRED_ARTIFACTS - declared_paths
    extra_required_artifacts = declared_paths - REQUIRED_ARTIFACTS
    if missing_artifacts:
        errors.append(f"missing required artifacts: {sorted(missing_artifacts)}")
    if extra_required_artifacts:
        errors.append(f"undeclared required artifact paths: {sorted(extra_required_artifacts)}")
    if len(artifacts) != EXPECTED_REQUIRED_ARTIFACT_COUNT:
        errors.append(f"artifact count must be {EXPECTED_REQUIRED_ARTIFACT_COUNT}")

    validation = manifest.get("validation")
    if not isinstance(validation, dict):
        errors.append("validation must be an object")
        validation = {}

    if validation.get("required_artifact_count") != EXPECTED_REQUIRED_ARTIFACT_COUNT:
        errors.append("validation.required_artifact_count must be 11")
    if validation.get("all_required_artifacts_present") is not True:
        errors.append("validation.all_required_artifacts_present must be true")
    if validation.get("readiness_passed") is not True:
        errors.append("validation.readiness_passed must be true")
    if validation.get("unknown_has_unclassified") is not False:
        errors.append("validation.unknown_has_unclassified must be false")
    if validation.get("san_juan_bias_explained") is not True:
        errors.append("validation.san_juan_bias_explained must be true")
    if int(validation.get("graph_edges_missing_confidence") or 0) > 0:
        errors.append("graph edges missing confidence")
    if int(validation.get("graph_edges_missing_lineage") or 0) > 0:
        errors.append("graph edges missing lineage")
    if int(validation.get("false_pr_municipio_code_count") or 0) > 0:
        errors.append("false PR municipio codes remain")
    if validation.get("input_record_count") != validation.get("density_record_count"):
        errors.append("input/density record counts do not reconcile")
    if float(validation.get("input_total_amount") or 0) != float(validation.get("density_total_amount") or 0):
        errors.append("input/density total amounts do not reconcile")

    return {
        "status": "READY" if not errors else "BLOCKED",
        "errors": errors,
        "producer_repository": producer.get("repository"),
        "producer_commit": producer.get("commit"),
        "artifact_count": len(artifacts),
        "required_artifact_count": EXPECTED_REQUIRED_ARTIFACT_COUNT,
        "declared_paths": sorted(declared_paths),
    }


def validate_contract_finance_manifest(manifest_path: str | Path) -> dict[str, Any]:
    report = assess_contract_finance_manifest(manifest_path)
    if report["errors"]:
        raise ContractFinanceManifestGateError("; ".join(report["errors"]))
    return report
