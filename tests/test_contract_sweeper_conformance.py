"""Cross-repo conformance test for the Contract-Sweeper → spiderweb-pr handoff.

This guards against the contract-drift incident documented in
``docs/contracts/CONTRACT_FINANCE_CONNECTIVITY_HEALTH.md``: the two repos had
independently shipped incompatible "1.1.0" export contracts, so the consumer
rejected the producer's real package. The shared v1.2.0 conformance package in
``tests/fixtures/contract_sweeper_v1_2/`` is byte-identical to the copy committed
in Contract-Sweeper (``exports/conformance/v1_2/``) and is produced by the
producer's own ``scripts/build_export_package.py``. If either side changes the
on-wire shape without re-syncing, this test fails.
"""

from __future__ import annotations

from pathlib import Path

from federation.hub.adapters.contract_sweeper import (
    EXPECTED_VERSION,
    export_contract_sweeper_features,
    load_contract_sweeper_package,
)
from federation.hub.layer_registry import get_layer_entry
from readiness.contract_finance_layer import build_contract_finance_layer
from readiness.contract_sweeper_package_gate import assess_contract_sweeper_package

FIXTURE = Path(__file__).parent / "fixtures" / "contract_sweeper_v1_2"


def test_version_pins_agree():
    assert EXPECTED_VERSION == "1.2.0"
    assert get_layer_entry("contract_finance").export_contract_version == "1.2.0"


def test_producer_package_loads_in_production_mode():
    package = load_contract_sweeper_package(FIXTURE, mode="production")
    assert package.producer == "contract-sweeper"
    assert package.version == "1.2.0"
    assert set(package.streams) == {
        "entities",
        "sources",
        "funding_awards",
        "transactions",
        "relationships",
    }


def test_production_gate_is_ready_not_blocked():
    report = assess_contract_sweeper_package(FIXTURE)
    assert report["status"] == "READY"
    assert report["blockers"] == []
    assert report["export_contract_version"] == "1.2.0"
    # canonical latitude/longitude coordinates must be read as point geometry
    assert report["metrics"]["point_geometry_coverage"] == 1.0
    assert report["metrics"]["municipality_coverage"] == 1.0


def test_full_round_trip_scores(tmp_path):
    adapter_out = tmp_path / "adapter"
    layer_out = tmp_path / "layer"
    report = export_contract_sweeper_features(FIXTURE, adapter_out, mode="production")
    assert report["counts"]["contract_awards"] == 2
    assert report["counts"]["financial_flows"] == 1

    layer = build_contract_finance_layer(adapter_out, layer_out)
    assert layer["status"] == "READY"
    assert layer["record_count"] == 3
    assert (layer_out / "contract_finance_scored_overlay.geojson").exists()
