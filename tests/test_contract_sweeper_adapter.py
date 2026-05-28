from __future__ import annotations

import json
from pathlib import Path

import pytest

from federation.hub.adapters.contract_sweeper import (
    ContractSweeperAdapterError,
    export_contract_sweeper_features,
    load_contract_sweeper_package,
    normalize_contract_sweeper_records,
)

FIXTURE = Path(__file__).parent / "fixtures" / "contract_sweeper_v1_1"


def test_load_contract_sweeper_v1_1_fixture():
    package = load_contract_sweeper_package(FIXTURE, mode="test")

    assert package.producer == "contract-sweeper"
    assert package.version == "1.1.0"
    assert set(package.streams) == {
        "entities",
        "sources",
        "funding_awards",
        "transactions",
        "relationships",
    }
    assert len(package.streams["funding_awards"]) == 2


def test_normalize_contract_sweeper_features():
    package = load_contract_sweeper_package(FIXTURE, mode="test")
    normalized = normalize_contract_sweeper_records(package)

    assert len(normalized["contract_awards"]) == 2
    assert len(normalized["financial_flows"]) == 1
    assert normalized["contract_awards"][0]["geometry"]["type"] == "Point"
    assert normalized["contract_awards"][0]["properties"]["entity"]["external_ids"]["uei"] == "UEI000000001"
    assert normalized["municipality_funding_density"][0]["municipality_code"] == "72113"


def test_export_contract_sweeper_outputs(tmp_path):
    report = export_contract_sweeper_features(FIXTURE, tmp_path, mode="test")

    assert report["export_contract_version"] == "1.1.0"
    assert (tmp_path / "contract_awards.geojson").exists()
    assert (tmp_path / "financial_flows.geojson").exists()
    assert (tmp_path / "municipality_funding_density.csv").exists()
    assert (tmp_path / "entity_graph.graphml").exists()
    assert (tmp_path / "contract_finance_ingest_report.json").exists()

    awards = json.loads((tmp_path / "contract_awards.geojson").read_text(encoding="utf-8"))
    assert awards["type"] == "FeatureCollection"
    assert len(awards["features"]) == 2


def test_reject_synthetic_record_in_production(tmp_path):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    for src in FIXTURE.iterdir():
        (package_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    rows = (package_dir / "transactions.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(rows[0])
    row["synthetic"] = True
    (package_dir / "transactions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ContractSweeperAdapterError, match="synthetic"):
        load_contract_sweeper_package(package_dir, mode="production")
