from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from federation.hub.adapters.contract_sweeper import export_contract_sweeper_features
from federation.hub.layer_registry import get_layer_entry
from readiness.contract_finance_layer import ContractFinanceLayerError, build_contract_finance_layer

FIXTURE = Path(__file__).parent / "fixtures" / "contract_sweeper_v1_2"
MANIFEST_FIXTURE = Path(__file__).parent / "fixtures" / "contract_finance_artifact_manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))


def _write_manifest(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "artifact_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_contract_finance_layer_registry_entry():
    entry = get_layer_entry("contract_finance")

    assert entry.producer == "contract-sweeper"
    assert entry.export_contract_version == "1.2.0"
    assert entry.manifest_gate_module == "readiness.contract_finance_manifest_gate"
    assert entry.manifest_gate_argument == "--artifact-manifest"
    assert entry.manifest_artifact == "artifact_manifest.json"
    assert "artifact_manifest.json" in entry.input_artifacts
    assert "entity_convergence" in entry.score_features
    assert "municipal_density" in entry.score_features
    assert "temporal_funding_pulse" in entry.score_features


def test_contract_finance_layer_scores_adapter_outputs(tmp_path):
    adapter_out = tmp_path / "adapter"
    layer_out = tmp_path / "layer"

    export_contract_sweeper_features(FIXTURE, adapter_out, mode="test")
    report = build_contract_finance_layer(adapter_out, layer_out)

    assert report["status"] == "READY"
    assert report["record_count"] == 3
    assert report["producer"] == "contract-sweeper"
    assert report["export_contract_version"] == "1.2.0"

    overlay_path = layer_out / "contract_finance_scored_overlay.geojson"
    report_path = layer_out / "contract_finance_layer_report.json"
    assert overlay_path.exists()
    assert report_path.exists()

    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    assert overlay["type"] == "FeatureCollection"
    assert len(overlay["features"]) == 3
    first_props = overlay["features"][0]["properties"]
    assert first_props["source_layer"] == "contract_finance"
    assert first_props["spiderweb_score"] > 0
    assert set(first_props["score_components"]) == {
        "amount_weight",
        "entity_convergence",
        "municipal_density",
        "temporal_funding_pulse",
    }


def test_contract_finance_layer_accepts_valid_artifact_manifest(tmp_path):
    adapter_out = tmp_path / "adapter"
    layer_out = tmp_path / "layer"

    export_contract_sweeper_features(FIXTURE, adapter_out, mode="test")
    report = build_contract_finance_layer(adapter_out, layer_out, artifact_manifest=MANIFEST_FIXTURE)

    assert report["status"] == "READY"
    assert report["artifact_manifest_gate"]["status"] == "READY"
    assert report["artifact_manifest_gate"]["producer_repository"] == "jotaele44/Contract-Sweeper"
    assert report["artifact_manifest_gate"]["artifact_count"] == 11


def test_contract_finance_layer_blocks_bad_artifact_manifest(tmp_path):
    adapter_out = tmp_path / "adapter"
    layer_out = tmp_path / "layer"
    bad_manifest = copy.deepcopy(_manifest())
    bad_manifest["validation"]["readiness_passed"] = False
    manifest_path = _write_manifest(tmp_path, bad_manifest)

    export_contract_sweeper_features(FIXTURE, adapter_out, mode="test")

    with pytest.raises(ContractFinanceLayerError, match="artifact manifest gate failed"):
        build_contract_finance_layer(adapter_out, layer_out, artifact_manifest=manifest_path)

    assert not (layer_out / "contract_finance_scored_overlay.geojson").exists()
