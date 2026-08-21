import json
from pathlib import Path

from spiderweb.subsurface.relevance_v11 import harden_relevance


def _zone(score=4.05, tier="SUPPORTING"):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}, "properties": {"zone_id": "Z1", "score": score, "relevance": "MODERATE", "evidence_tier": tier}}


def _feature(record_id, source_id, family, attrs=None):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0.5,0.5]}, "properties": {"record_id": record_id, "source_id": source_id, "layer_family": family, "spatial_state": "FULLY_WITHIN", "attributes": attrs or {}}}


def test_v11_uses_canonical_groundwater_assets_not_duplicate_rows():
    v1 = {"type": "FeatureCollection", "features": [_zone()]}
    evidence = {"type": "FeatureCollection", "features": [
        _feature("a", "PRPB_WELLS_JCA_20", "AQUIFERS_WELLS_SPRINGS"),
        _feature("b", "PRPB_WELLS_AAA_21", "AQUIFERS_WELLS_SPRINGS"),
    ]}
    assets = {"assets": [{"canonical_id": "GW1", "asset_class": "GROUNDWATER_POINT", "member_record_ids": ["a", "b"]}]}
    out = harden_relevance(v1, evidence, assets)["features"][0]["properties"]
    assert out["canonical_groundwater_assets"] == 1


def test_v11_never_uses_military_family_in_score():
    v1 = {"type": "FeatureCollection", "features": [_zone()]}
    evidence = {"type": "FeatureCollection", "features": [
        _feature("m", "X", "MILITARY_HARDENED_SUBSURFACE"),
    ]}
    out = harden_relevance(v1, evidence, {"assets": []})["features"][0]["properties"]
    assert out["v11_score"] == 0.0
    assert out["v11_relevance"] == "VERY_LOW"


def test_v11_marks_canonical_threshold_drop_provisional():
    v1 = {"type": "FeatureCollection", "features": [_zone()]}
    evidence = {"type": "FeatureCollection", "features": []}
    out = harden_relevance(v1, evidence, {"assets": []})["features"][0]["properties"]
    assert out["v11_relevance"] == "VERY_LOW"
    assert out["sensitivity_state"] == "PROVISIONAL"


def test_v11_direct_cave_zone_can_be_robust_without_connectivity_claim():
    v1 = {"type": "FeatureCollection", "features": [_zone(6.0, "DIRECT")]}
    evidence = {"type": "FeatureCollection", "features": [
        _feature("c", "PRPB_CAVES_31", "GEOLOGY_KARST_CAVES"),
        _feature("q", "PRPB_QUARRIES_10", "MINES_QUARRIES_SHAFTS"),
        _feature("h", "USGS_TOPOVIEW_OVERLAY_0", "HISTORICAL_CORROBORATION"),
        _feature("u", "PRPB_AAA_WATER_MAIN_3", "UTILITIES_UNDERGROUND"),
    ]}
    assets = {"assets": [{"canonical_id": "Q1", "asset_class": "MINE_QUARRY_FEATURE", "member_record_ids": ["q"]}]}
    out = harden_relevance(v1, evidence, assets)["features"][0]["properties"]
    assert out["v11_relevance"] in {"MODERATE", "HIGH"}
    assert out["sensitivity_state"] == "ROBUST"
