from __future__ import annotations

import hashlib
import json

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


def component_receipt(raw: bytes = COMPONENT) -> dict:
    return {
        "provider_id": "SSURGO_SOILS",
        "request_role": "component",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_stage3_freezes_cokey_denominator_and_current_child_contract() -> None:
    contract = {
        "tables": [
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
        "invariants": {"table_count": 2},
    }
    plan = build_stage3_child_plan(
        query={"query_id": "x"},
        component_raw=COMPONENT,
        component_receipt=component_receipt(),
        child_contract=contract,
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
            child_contract={"tables": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}], "invariants": {"table_count": 1}},
        )


def test_stage3_child_contract_count_drift_fails_closed() -> None:
    with pytest.raises(SSURGOChainError, match="table_count invariant drift"):
        build_stage3_child_plan(
            query={"query_id": "x"},
            component_raw=COMPONENT,
            component_receipt=component_receipt(),
            child_contract={
                "tables": [{"table": "chorizon", "stable_key": "chkey", "parent_key": "cokey"}],
                "invariants": {"table_count": 2},
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
