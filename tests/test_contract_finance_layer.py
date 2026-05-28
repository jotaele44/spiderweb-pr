from __future__ import annotations

import json
from pathlib import Path

from federation.hub.adapters.contract_sweeper import export_contract_sweeper_features
from federation.hub.layer_registry import get_layer_entry
from readiness.contract_finance_layer import build_contract_finance_layer

FIXTURE = Path(__file__).parent / "fixtures" / "contract_sweeper_v1_1"


def test_contract_finance_layer_registry_entry():
    entry = get_layer_entry("contract_finance")

    assert entry.producer == "contract-sweeper"
    assert entry.export_contract_version == "1.1.0"
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
    assert report["export_contract_version"] == "1.1.0"

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
