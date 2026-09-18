from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from spiderweb.ssurgo_chain import (
    SSURGOChainError,
    build_stage2_plan,
    build_stage3_child_plan,
    certify_child_table_response,
)


GML = b"""<?xml version="1.0"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs" xmlns:ssurgo="urn:ssurgo">
  <gml:featureMember xmlns:gml="http://www.opengis.net/gml"><ssurgo:MapunitPoly><ssurgo:mukey>326637</ssurgo:mukey></ssurgo:MapunitPoly></gml:featureMember>
  <gml:featureMember xmlns:gml="http://www.opengis.net/gml"><ssurgo:MapunitPoly><ssurgo:mukey>326638</ssurgo:mukey></ssurgo:MapunitPoly></gml:featureMember>
  <gml:featureMember xmlns:gml="http://www.opengis.net/gml"><ssurgo:MapunitPoly><ssurgo:mukey>326637</ssurgo:mukey></ssurgo:MapunitPoly></gml:featureMember>
</wfs:FeatureCollection>
"""


def receipt(raw: bytes = GML) -> dict:
    return {
        "provider_id": "SSURGO_SOILS",
        "request_role": "MapunitPoly",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_stage2_freezes_unique_mukey_denominator_and_two_post_requests() -> None:
    plan = build_stage2_plan(query={"query_id": "x", "mode": "fetch"}, mapunitpoly_raw=GML, mapunitpoly_receipt=receipt())
    assert plan["ssurgo_denominator"]["mukeys"] == ["326637", "326638"]
    assert plan["ssurgo_denominator"]["mukey_count"] == 2
    assert plan["request_count"] == 2
    assert {r["request_role"] for r in plan["requests"]} == {"mapunit", "component"}
    assert all(r["method"] == "POST" for r in plan["requests"])
    assert all(
        r["parent_denominator_sha256"]
        == plan["ssurgo_denominator"]["canonical_mukey_set_sha256"]
        for r in plan["requests"]
    )
    assert all("WHERE mukey IN ('326637', '326638')" in r["json_body"]["query"] for r in plan["requests"])
    assert plan["policy"]["one_to_n_flattening"] is False


def test_stage2_fails_on_raw_receipt_hash_mismatch() -> None:
    bad = receipt()
    bad["sha256"] = "0" * 64
    with pytest.raises(SSURGOChainError):
        build_stage2_plan(query={"query_id": "x"}, mapunitpoly_raw=GML, mapunitpoly_receipt=bad)


def test_stage2_fails_on_non_numeric_mukey() -> None:
    raw = GML.replace(b"326638", b"BADKEY")
    with pytest.raises(SSURGOChainError):
        build_stage2_plan(query={"query_id": "x"}, mapunitpoly_raw=raw, mapunitpoly_receipt=receipt(raw))


COMPONENT = json.dumps({
    "Table": [
        ["compname", "mukey", "cokey"],
        ["A", "326637", "27625770"],
        ["B", "326638", "27625771"],
    ]
}).encode("utf-8")


def component_receipt(
    raw: bytes = COMPONENT,
    parent_mukeys: list[str] | None = None,
) -> dict:
    parent = ["326637", "326638"] if parent_mukeys is None else parent_mukeys
    return {
        "provider_id": "SSURGO_SOILS",
        "request_role": "component",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "parent_denominator_sha256": hashlib.sha256(
            ("\n".join(sorted(parent, key=int)) + "\n").encode()
        ).hexdigest(),
    }


def test_stage3_freezes_cokey_denominator_and_current_child_contract() -> None:
    contract = {
        "schema_version": "spiderweb.ssurgo_component_children.v1.1",
        "parent_table": "component",
        "parent_key": "cokey",
        "relationship_count": 2,
        "current_documentation_epoch": "fixture",
        "records": [
            {
                "table": "chorizon",
                "stable_key": "chkey",
                "parent_key": "cokey",
                "key_evidence": "UNIQUE_CONSTRAINT_REPORT",
                "cardinality": "0:N_or_1:N_table_specific",
            },
            {
                "table": "comonth",
                "stable_key": "comonthkey",
                "parent_key": "cokey",
                "key_evidence": "UNIQUE_CONSTRAINT_REPORT",
                "cardinality": "0:N_or_1:N_table_specific",
            },
        ],
        "lineage": {"prior_frozen_relationship_count": 1},
    }
    plan = build_stage3_child_plan(
        query={"query_id": "x"},
        component_raw=COMPONENT,
        component_receipt=component_receipt(),
        child_contract=contract,
        certified_mukeys=["326637", "326638"],
    )
    assert plan["fetch_gate"] == "READY"
    assert plan["ssurgo_cokey_denominator"]["cokeys"] == ["27625770", "27625771"]
    assert plan["ssurgo_cokey_denominator"]["cokey_count"] == 2
    assert plan["child_table_denominator"]["table_count"] == 2
    assert plan["request_count"] == 2
    assert all(r["protocol"] == "SDA_TABULAR" for r in plan["requests"])
    assert all(r["parent_denominator_sha256"] == plan["ssurgo_cokey_denominator"]["canonical_cokey_set_sha256"] for r in plan["requests"])
    assert all("WHERE cokey IN ('27625770', '27625771')" in r["json_body"]["query"] for r in plan["requests"])


def test_stage3_duplicate_component_cokey_fails_closed() -> None:
    raw = json.dumps({
        "Table": [
            ["mukey", "cokey"],
            ["326637", "27625770"],
            ["326637", "27625770"],
        ]
    }).encode("utf-8")
    with pytest.raises(SSURGOChainError, match="duplicate COKEYs"):
        build_stage3_child_plan(
            query={"query_id": "x"},
            component_raw=raw,
            component_receipt=component_receipt(raw),
            certified_mukeys=["326637", "326638"],
            child_contract={
                "schema_version": "spiderweb.ssurgo_component_children.v1.1",
                "parent_table": "component",
                "parent_key": "cokey",
                "relationship_count": 1,
                "records": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}],
            },
        )


def test_stage3_child_contract_count_drift_fails_closed() -> None:
    with pytest.raises(SSURGOChainError, match="relationship_count invariant drift"):
        build_stage3_child_plan(
            query={"query_id": "x"},
            component_raw=COMPONENT,
            component_receipt=component_receipt(),
            certified_mukeys=["326637", "326638"],
            child_contract={
                "schema_version": "spiderweb.ssurgo_component_children.v1.1",
                "parent_table": "component",
                "parent_key": "cokey",
                "relationship_count": 2,
                "records": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}],
            },
        )


def test_child_certification_allows_zero_child_parents_and_closes_arithmetic() -> None:
    raw = json.dumps({
        "Table": [
            ["cokey", "chkey", "hzname"],
            ["27625770", "1001", "A"],
            ["27625770", "1002", "B"],
        ]
    }).encode("utf-8")
    parent = ["27625770", "27625771"]
    receipt = {
        "provider_id": "SSURGO_SOILS",
        "request_role": "component_child:chorizon",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "parent_denominator_sha256": hashlib.sha256(("\n".join(parent) + "\n").encode()).hexdigest(),
    }
    out = certify_child_table_response(
        raw=raw,
        receipt=receipt,
        contract={"table": "chorizon", "parent_key": "cokey", "stable_key": "chkey"},
        certified_cokeys=parent,
    )
    assert out["state"] == "PASS"
    assert out["row_count"] == 2
    assert out["zero_child_parent_count"] == 1
    assert out["zero_child_parent_keys"] == ["27625771"]
    assert out["multi_child_parent_count"] == 1
    assert out["arithmetic_closure"] is True


def test_child_certification_rejects_foreign_parent() -> None:
    raw = json.dumps({
        "Table": [
            ["cokey", "chkey"],
            ["99999999", "1001"],
        ]
    }).encode("utf-8")
    parent = ["27625770"]
    receipt = {
        "provider_id": "SSURGO_SOILS",
        "request_role": "component_child:chorizon",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "parent_denominator_sha256": hashlib.sha256(("\n".join(parent) + "\n").encode()).hexdigest(),
    }
    with pytest.raises(SSURGOChainError, match="foreign parent COKEY"):
        certify_child_table_response(
            raw=raw,
            receipt=receipt,
            contract={"table": "chorizon", "parent_key": "cokey", "stable_key": "chkey"},
            certified_cokeys=parent,
        )


def test_child_certification_rejects_duplicate_stable_key() -> None:
    raw = json.dumps({
        "Table": [
            ["cokey", "chkey"],
            ["27625770", "1001"],
            ["27625770", "1001"],
        ]
    }).encode("utf-8")
    parent = ["27625770"]
    receipt = {
        "provider_id": "SSURGO_SOILS",
        "request_role": "component_child:chorizon",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "parent_denominator_sha256": hashlib.sha256(("\n".join(parent) + "\n").encode()).hexdigest(),
    }
    with pytest.raises(SSURGOChainError, match="duplicate stable keys"):
        certify_child_table_response(
            raw=raw,
            receipt=receipt,
            contract={"table": "chorizon", "parent_key": "cokey", "stable_key": "chkey"},
            certified_cokeys=parent,
        )


def test_current_component_child_contract_is_22_and_time_supersedes_21() -> None:
    root = Path(__file__).resolve().parents[1]
    contract = json.loads(
        (root / "configs/ssurgo_component_children.json").read_text(encoding="utf-8")
    )
    assert contract["schema_version"] == "spiderweb.ssurgo_component_children.v1.1"
    assert contract["parent_table"] == "component"
    assert contract["parent_key"] == "cokey"
    assert contract["relationship_count"] == 22
    assert len(contract["records"]) == 22
    assert len({row["table"] for row in contract["records"]}) == 22
    assert "coinundationtype" in {row["table"] for row in contract["records"]}
    assert contract["lineage"]["prior_frozen_relationship_count"] == 21
    assert contract["lineage"]["contradiction_class"] == "TIME"


def test_stage3_records_canonical_child_contract_hash() -> None:
    contract = {
        "schema_version": "spiderweb.ssurgo_component_children.v1.1",
        "parent_table": "component",
        "parent_key": "cokey",
        "relationship_count": 1,
        "records": [{
            "table": "chorizon",
            "stable_key": "chkey",
            "parent_key": "cokey",
        }],
    }
    plan = build_stage3_child_plan(
        query={"query_id": "x"},
        component_raw=COMPONENT,
        component_receipt=component_receipt(),
        child_contract=contract,
        certified_mukeys=["326637", "326638"],
    )
    expected = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert plan["child_table_denominator"]["canonical_contract_sha256"] == expected
    assert plan["requests"][0]["ssurgo_child_contract_sha256"] == expected


def test_stage3_rejects_component_parent_hash_mismatch() -> None:
    bad = component_receipt()
    bad["parent_denominator_sha256"] = "0" * 64
    with pytest.raises(SSURGOChainError, match="parent MUKEY denominator hash mismatch"):
        build_stage3_child_plan(
            query={"query_id": "x"},
            component_raw=COMPONENT,
            component_receipt=bad,
            child_contract={
                "schema_version": "spiderweb.ssurgo_component_children.v1.1",
                "parent_table": "component",
                "parent_key": "cokey",
                "relationship_count": 1,
                "records": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}],
            },
            certified_mukeys=["326637", "326638"],
        )


def test_stage3_rejects_foreign_component_mukey() -> None:
    raw = json.dumps({
        "Table": [
            ["mukey", "cokey"],
            ["326637", "27625770"],
            ["999999", "27625771"],
        ]
    }).encode("utf-8")
    with pytest.raises(SSURGOChainError, match="foreign MUKEYs"):
        build_stage3_child_plan(
            query={"query_id": "x"},
            component_raw=raw,
            component_receipt=component_receipt(raw),
            child_contract={
                "schema_version": "spiderweb.ssurgo_component_children.v1.1",
                "parent_table": "component",
                "parent_key": "cokey",
                "relationship_count": 1,
                "records": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}],
            },
            certified_mukeys=["326637", "326638"],
        )


def test_stage3_records_missing_parent_mukey_without_identity_inference() -> None:
    raw = json.dumps({
        "Table": [
            ["mukey", "cokey"],
            ["326637", "27625770"],
        ]
    }).encode("utf-8")
    plan = build_stage3_child_plan(
        query={"query_id": "x"},
        component_raw=raw,
        component_receipt=component_receipt(raw),
        child_contract={
            "schema_version": "spiderweb.ssurgo_component_children.v1.1",
            "parent_table": "component",
            "parent_key": "cokey",
            "relationship_count": 1,
            "records": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}],
        },
        certified_mukeys=["326637", "326638"],
    )
    assert plan["component_parent"]["foreign_mukey_count"] == 0
    assert plan["component_parent"]["missing_mukey_count"] == 1
    assert plan["component_parent"]["missing_mukeys"] == ["326638"]
    assert plan["component_parent"]["returned_parent_subset"] is True
