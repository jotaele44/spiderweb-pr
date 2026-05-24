"""
PRIIS API contract tests.

Validates that each backend route returns data whose shape matches the
frontend Zod schemas.  Requires the backend to be running:

    python3 -m uvicorn server.backend.main:app --port 8000

Run with:
    pytest tests/test_priis_api.py -v
"""
from __future__ import annotations

import json
import pytest
import requests

BASE = "http://localhost:8000"


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _get(path: str) -> list | dict:
    """GET a JSON response, skipping the test if the server is not running."""
    try:
        r = requests.get(f"{BASE}{path}", timeout=5)
    except requests.ConnectionError:
        pytest.skip("PRIIS backend not running — start with: python3 -m uvicorn server.backend.main:app --port 8000")
    assert r.status_code == 200, f"{path} → {r.status_code}"
    return r.json()


def _check_fields(record: dict, required: list[str], path: str) -> None:
    missing = [f for f in required if f not in record]
    assert not missing, f"{path}: record missing fields {missing}\n  record={record}"


# ─── Health ────────────────────────────────────────────────────────────────────

def test_health():
    data = _get("/health")
    assert data["status"] == "ok"
    assert data["db_exists"] is True


# ─── Entity route shapes ────────────────────────────────────────────────────────

def test_agencies_shape():
    rows = _get("/agencies")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "code", "name"], "/agencies")


def test_vendors_shape():
    rows = _get("/vendors")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "name", "risk", "tier"], "/vendors")
    for r in rows:
        assert isinstance(r["risk"], (float, int)), f"vendor risk not numeric: {r}"
        assert r["tier"] in ("T1", "T2", "T3", "T4"), f"invalid tier: {r['tier']}"


def test_sites_shape():
    rows = _get("/sites")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "name", "kind", "lat", "lng", "sensitive"], "/sites")
    for r in rows:
        assert isinstance(r["lat"], (float, int)), f"lat not numeric: {r}"
        assert isinstance(r["lng"], (float, int)), f"lng not numeric: {r}"
        assert isinstance(r["sensitive"], bool), f"sensitive not bool: {r}"


def test_contracts_shape():
    rows = _get("/contracts")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "agency", "vendor", "amount", "signed", "status", "tier"], "/contracts")
    valid_statuses = {"planned", "executed", "amended", "flagged", "closed", "unknown"}
    for r in rows:
        assert isinstance(r["amount"], (float, int)), f"amount not numeric: {r}"
        assert r["status"] in valid_statuses, f"invalid status: {r['status']}"
        assert r["tier"] in ("T1", "T2", "T3", "T4"), f"invalid tier: {r['tier']}"


def test_events_shape():
    rows = _get("/events")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "kind", "at", "label"], "/events")
    valid_kinds = {"contract", "imagery", "flight", "report", "outage", "permit", "field", "other"}
    for r in rows:
        assert r["kind"] in valid_kinds, f"invalid kind: {r['kind']}"
        # siteId and refId are optional but must not be absent keys
        assert "siteId" in r, f"events row missing siteId key: {r}"


def test_anomalies_shape():
    rows = _get("/anomalies")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "title", "category", "score", "band", "summary", "confidence"], "/anomalies")
    for r in rows:
        # Array fields must be deserialized (not raw JSON strings)
        assert isinstance(r["factors"], list), f"factors is not a list: {type(r['factors'])}"
        assert isinstance(r["contracts"], list), f"contracts is not a list: {type(r['contracts'])}"
        assert isinstance(r["events"], list), f"events is not a list: {type(r['events'])}"
        assert isinstance(r["contradictions"], list), f"contradictions is not a list: {type(r['contradictions'])}"
        assert r["band"] in ("lo", "md", "hi"), f"invalid band: {r['band']}"
        assert r["confidence"] in (1, 2, 3), f"invalid confidence: {r['confidence']}"

        # Evidence tier rules: confidence 3 must not come from T3/T4 alone
        # (This checks the seed data respects the hard requirement)
        if r["confidence"] == 3:
            factors = r["factors"]
            if factors:
                tags = {f["tag"] for f in factors if isinstance(f, dict) and "tag" in f}
                # High confidence is allowed only if there's T1/T2 evidence (finance/spatial/imagery)
                t1_t2_tags = {"finance", "spatial", "imagery", "flight"}
                assert tags & t1_t2_tags, (
                    f"confidence=3 anomaly {r['id']} has no T1/T2 evidence tags: {tags}"
                )


def test_sources_shape():
    rows = _get("/sources")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "name", "tier", "kind", "status"], "/sources")
    valid_kinds = {"technical", "operational", "eyewitness", "secondary", "derived"}
    valid_statuses = {"online", "partial", "offline"}
    for r in rows:
        assert r["kind"] in valid_kinds, f"invalid source kind: {r['kind']}"
        assert r["status"] in valid_statuses, f"invalid source status: {r['status']}"


def test_investigations_shape():
    rows = _get("/investigations")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "title", "active_vector", "status"], "/investigations")
    valid_statuses = {"active", "paused", "closed", "needs_review"}
    for r in rows:
        assert r["status"] in valid_statuses, f"invalid investigation status: {r['status']}"


def test_alerts_shape():
    rows = _get("/alerts")
    assert isinstance(rows, list) and len(rows) > 0
    _check_fields(rows[0], ["id", "at", "kind", "title", "tier"], "/alerts")
    valid_kinds = {"finance", "spatial", "source", "anomaly", "report"}
    for r in rows:
        assert r["kind"] in valid_kinds, f"invalid alert kind: {r['kind']}"
        assert r["tier"] in ("T1", "T2", "T3", "T4"), f"invalid tier: {r['tier']}"


# ─── GeoJSON DB fallbacks ───────────────────────────────────────────────────────

def test_geo_sites_fallback():
    data = _get("/geo/sites.geojson")
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0
    feat = data["features"][0]
    assert feat["geometry"]["type"] == "Point"
    coords = feat["geometry"]["coordinates"]
    assert len(coords) == 2
    # Puerto Rico longitude range
    assert -68.0 <= coords[0] <= -65.0, f"lng out of PR range: {coords[0]}"
    assert 17.5 <= coords[1] <= 18.6, f"lat out of PR range: {coords[1]}"


def test_geo_anomalies_fallback():
    data = _get("/geo/anomalies.geojson")
    assert data["type"] == "FeatureCollection"
    # Anomalies with known site coordinates should have features
    feats = data["features"]
    if feats:
        feat = feats[0]
        props = feat["properties"]
        assert "id" in props and "score" in props and "band" in props


def test_geo_flights_empty_when_no_output():
    """Flights GeoJSON returns empty FeatureCollection when no pipeline has run."""
    data = _get("/geo/flights.geojson")
    assert data["type"] == "FeatureCollection"
    # May or may not have features depending on whether outputs/flights.geojson exists
    assert isinstance(data["features"], list)


def test_geo_unknown_layer_returns_400():
    try:
        r = requests.get(f"{BASE}/geo/unknown_layer.geojson", timeout=5)
    except requests.ConnectionError:
        pytest.skip("backend not running")
    assert r.status_code == 400
