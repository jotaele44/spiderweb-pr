from __future__ import annotations

import hashlib

import pytest

from spiderweb.ssurgo_chain import SSURGOChainError, build_stage2_plan


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
