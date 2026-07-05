from __future__ import annotations

import json
from pathlib import Path

from federation.hub.adapters.moneysweep import export_moneysweep_features
from readiness.contract_finance_calibration import calibrate_contract_finance_layer
from readiness.contract_finance_fusion import fuse_contract_finance_scores
from readiness.contract_finance_layer import build_contract_finance_layer
from readiness.moneysweep_package_gate import assess_moneysweep_package

FIXTURE = Path(__file__).parent / "fixtures" / "moneysweep_v1_2"
AIRSPACE_FIXTURE = Path(__file__).parent / "fixtures" / "airspace_overlay_for_contract_fusion.geojson"


def test_moneysweep_package_gate_accepts_fixture_as_degraded_not_blocked():
    report = assess_moneysweep_package(FIXTURE)

    assert report["producer"] == "moneysweep-pr"
    assert report["export_contract_version"] == "1.2.0"
    assert report["status"] in {"READY", "DEGRADED"}
    assert report["metrics"]["money_rows"] == 3
    assert report["blockers"] == []


def test_contract_finance_calibration_report(tmp_path):
    adapter_out = tmp_path / "adapter"
    export_moneysweep_features(FIXTURE, adapter_out, mode="test")
    build_contract_finance_layer(adapter_out)

    report = calibrate_contract_finance_layer(adapter_out)

    assert report["records"]["combined_money_features"] == 3
    assert report["coverage"]["municipality"] == 1.0
    assert report["amount_profile"]["nonzero_count"] == 3
    assert (adapter_out / "contract_finance_calibration_report.json").exists()


def test_contract_finance_fusion_report_and_overlay(tmp_path):
    adapter_out = tmp_path / "adapter"
    fusion_out = tmp_path / "fusion"
    export_moneysweep_features(FIXTURE, adapter_out, mode="test")
    build_contract_finance_layer(adapter_out)

    report = fuse_contract_finance_scores(
        AIRSPACE_FIXTURE,
        adapter_out / "contract_finance_scored_overlay.geojson",
        fusion_out,
    )

    assert report["candidate_count"] == 2
    assert report["matched_candidates"] >= 1
    overlay = json.loads((fusion_out / "spiderweb_fused_contract_finance_overlay.geojson").read_text(encoding="utf-8"))
    assert overlay["type"] == "FeatureCollection"
    assert len(overlay["features"]) == 2
    best = overlay["features"][0]["properties"]
    assert best["fused_spiderweb_score"] >= best["base_spiderweb_score"]
    assert "contract_finance_match" in best
