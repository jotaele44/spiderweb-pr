"""Decoupled unit tests for the contract/finance layer, fusion, and calibration.

These modules feed the static dashboard and stay in the producer-only tree; their
former tests were coupled to the retired query-hub (now under docs/legacy/). This
suite exercises the pure scoring/fusion/calibration logic directly — no federation
query-hub, no moneysweep-pr adapter.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from readiness.contract_finance_calibration import (
    _amount_profile,
    _coverage,
    _quantile,
    calibrate_contract_finance_layer,
)
from readiness.contract_finance_fusion import (
    _base_candidate_score,
    _best_contract_match,
    _coords,
    _safe_score,
    fuse_contract_finance_scores,
)
from readiness.contract_finance_layer import (
    _amount_score,
    _entity_convergence,
    _municipal_density_score,
    _score_features,
    _temporal_pulse,
    _tier,
    build_contract_finance_layer,
)
from collections import Counter


def _point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


def _feature(record_id, *, lon=-66.1, lat=18.4, entity_id="E1", amount=1000.0,
             muni="M1", date=None):
    return {
        "type": "Feature",
        "geometry": _point(lon, lat),
        "properties": {
            "record_id": record_id, "entity_id": entity_id, "amount": amount,
            "municipality_code": muni, "feature_type": "award",
            "date": date or "2026-05-01T00:00:00Z",
        },
    }


# ── contract_finance_layer: scoring formulas ─────────────────────────────────

def test_amount_score_bounds_and_monotonicity():
    assert _amount_score(0, 1000) == 0.0
    assert _amount_score(1000, 0) == 0.0
    assert _amount_score(1000, 1000) == 1.0
    assert 0.0 < _amount_score(100, 1000) < _amount_score(500, 1000) < 1.0


def test_entity_convergence_tiers():
    counts = Counter({"E1": 1, "E2": 2, "E3": 5})
    assert _entity_convergence("", counts) == 0.0
    assert _entity_convergence("E1", counts) == 0.35
    assert _entity_convergence("E2", counts) == 0.70
    assert _entity_convergence("E3", counts) == 1.0


def test_municipal_density_score():
    density = {"M1": {"total_amount": 50.0}, "M2": {"total_amount": 100.0}}
    assert _municipal_density_score("M2", density, 100.0) == 1.0
    assert _municipal_density_score("M1", density, 100.0) == 0.5
    assert _municipal_density_score("MISSING", density, 100.0) == 0.0
    assert _municipal_density_score("M1", density, 0.0) == 0.0


def test_temporal_pulse_decay():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert _temporal_pulse((now - timedelta(days=10)).isoformat(), now) == 1.0
    assert _temporal_pulse((now - timedelta(days=500)).isoformat(), now) == 0.55
    assert _temporal_pulse((now - timedelta(days=900)).isoformat(), now) == 0.20
    assert _temporal_pulse("not-a-date", now) == 0.0


def test_tier_boundaries():
    assert _tier(0.75) == "T1"
    assert _tier(0.74) == "T2"
    assert _tier(0.55) == "T2"
    assert _tier(0.35) == "T3"
    assert _tier(0.0) == "T4"


def test_score_features_end_to_end():
    feats = [_feature("a", entity_id="E1", amount=1000), _feature("b", entity_id="E1", amount=10)]
    density = {"M1": {"total_amount": 1000.0}}
    scored = _score_features(feats, density)
    assert len(scored) == 2
    for f in scored:
        p = f["properties"]
        assert 0.0 <= p["spiderweb_score"] <= 1.0
        assert p["evidence_tier"] in {"T1", "T2", "T3", "T4"}
        assert set(p["score_components"]) == {
            "amount_weight", "entity_convergence", "municipal_density", "temporal_funding_pulse"}
        assert p["review_status"] in {"accepted", "manual_review"}
    # higher-amount feature sorts first (descending score)
    assert scored[0]["properties"]["record_id"] == "a"


# ── contract_finance_fusion ──────────────────────────────────────────────────

def test_coords_and_safe_score():
    assert _coords({"geometry": _point(-66.1, 18.4)}) == (18.4, -66.1)
    assert _coords({"geometry": {"type": "LineString", "coordinates": []}}) is None
    assert _safe_score("0.5") == 0.5
    assert _safe_score(2.0) == 1.0      # clamped
    assert _safe_score(-1.0) == 0.0
    assert _safe_score("nope") == 0.0


def test_base_candidate_score_prefers_explicit_then_tier():
    assert _base_candidate_score({"spiderweb_score": 0.42}) == 0.42
    assert _base_candidate_score({"confidence": 0.8}) == 0.8
    assert _base_candidate_score({"evidence_tier": "T2"}) == 0.65
    assert _base_candidate_score({}) == 0.0


def test_best_contract_match_relations():
    contracts = [
        {"coords": (18.4, -66.1), "score": 0.9, "municipality_code": "M1",
         "municipality_name": "Aguada", "record_id": "c1"},
    ]
    near = {"geometry": _point(-66.1, 18.4001), "properties": {"municipality_code": "ZZ"}}
    m = _best_contract_match(near, contracts, 0.045)
    assert m and m["match_relation"] == "point_proximity"

    by_code = {"geometry": {"type": "LineString"}, "properties": {"municipality_code": "M1"}}
    assert _best_contract_match(by_code, contracts, 0.045)["match_relation"] == "municipality_code"

    no_match = {"geometry": {"type": "LineString"}, "properties": {"municipality_code": "ZZ"}}
    assert _best_contract_match(no_match, contracts, 0.045) is None


def test_fuse_contract_finance_scores_end_to_end(tmp_path):
    air = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": _point(-66.1, 18.4),
         "properties": {"candidate_type": "poi", "evidence_tier": "T3", "municipality_code": "M1"}},
    ]}
    contracts = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": _point(-66.1, 18.4),
         "properties": {"record_id": "c1", "spiderweb_score": 0.8, "municipality_code": "M1"}},
    ]}
    (tmp_path / "air.geojson").write_text(json.dumps(air))
    (tmp_path / "contracts.geojson").write_text(json.dumps(contracts))
    report = fuse_contract_finance_scores(
        tmp_path / "air.geojson", tmp_path / "contracts.geojson", tmp_path / "out")
    assert report["candidate_count"] == 1
    assert report["matched_candidates"] == 1
    assert report["match_rate"] == 1.0
    fused = json.loads((tmp_path / "out" / "spiderweb_fused_contract_finance_overlay.geojson").read_text())
    p = fused["features"][0]["properties"]
    assert p["fused_spiderweb_score"] >= p["base_spiderweb_score"]


# ── contract_finance_calibration ─────────────────────────────────────────────

def test_quantile():
    assert _quantile([], 0.5) is None
    assert _quantile([10.0], 0.9) == 10.0
    assert _quantile([0.0, 10.0], 0.5) == 5.0      # interpolated midpoint
    assert _quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5


def test_amount_profile_and_coverage():
    feats = [_feature("a", amount=100), _feature("b", amount=0), _feature("c", amount=300)]
    prof = _amount_profile(feats)
    assert prof["count"] == 3
    assert prof["nonzero_count"] == 2
    assert prof["sum"] == 400.0
    assert prof["max"] == 300.0
    # all three have a municipality_code → full coverage
    assert _coverage(feats, lambda f: bool(f["properties"].get("municipality_code"))) == 1.0
    assert _coverage([], lambda f: True) == 0.0


def test_build_and_calibrate_end_to_end(tmp_path):
    awards = {"type": "FeatureCollection", "features": [_feature("a", amount=1000)]}
    flows = {"type": "FeatureCollection", "features": [_feature("b", amount=500, entity_id="E2")]}
    (tmp_path / "contract_awards.geojson").write_text(json.dumps(awards))
    (tmp_path / "financial_flows.geojson").write_text(json.dumps(flows))
    (tmp_path / "municipality_funding_density.csv").write_text(
        "municipality_code,municipality_name,total_amount,record_count\nM1,Aguada,1500,2\n")
    (tmp_path / "contract_finance_ingest_report.json").write_text(
        json.dumps({"producer": "moneysweep-pr", "export_contract_version": "1.2.0"}))

    report = build_contract_finance_layer(tmp_path)
    assert report["record_count"] == 2
    assert report["status"] == "READY"
    assert (tmp_path / "contract_finance_scored_overlay.geojson").exists()

    calib = calibrate_contract_finance_layer(tmp_path)
    assert calib["records"]["combined_money_features"] == 2
    assert calib["coverage"]["municipality"] == 1.0
    assert calib["score_profile"]["count"] == 2  # scored overlay present
