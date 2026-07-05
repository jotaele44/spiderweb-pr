"""Tests for the spatial + external-id cross-producer correlation strategies (G3-C2)."""
from federation.hub.index import record_external_ids, record_point
from federation.hub.query import correlate_by_external_id, correlate_spatial


def _rec(producer, rid, lat=None, lon=None, xid=None, score=0.9):
    rec = {"producer": producer, "record_id": rid, "confidence": {"score": score}, "entities": []}
    if lat is not None:
        rec["location"] = {"lat": lat, "lon": lon}
    if xid:
        rec["entities"] = [{"normalized_name": "ACME", "external_ids": {"uei": xid}}]
    return rec


def test_spatial_links_close_cross_producer():
    a = _rec("moneysweep-pr", "A", lat=18.45, lon=-66.06)
    b = _rec("spiderweb-pr", "B", lat=18.451, lon=-66.061)   # ~0.15 km away
    far = _rec("spiderweb-pr", "C", lat=18.0, lon=-67.0)     # far
    links = correlate_spatial([a, b, far], threshold_km=1.0)
    pairs = {(l["source_record_id"], l["target_record_id"]) for l in links}
    assert ("A", "B") in pairs
    assert ("A", "C") not in pairs and ("B", "C") not in pairs
    assert all(l["link_type"] == "spatial_proximity" and l["match_basis"] == "location" for l in links)


def test_spatial_skips_same_producer():
    a = _rec("p", "A", 18.45, -66.06)
    b = _rec("p", "B", 18.45, -66.06)
    assert correlate_spatial([a, b]) == []


def test_external_id_links_cross_producer():
    a = _rec("moneysweep-pr", "A", xid="UEI123")
    b = _rec("spiderweb-pr", "B", xid="UEI123")
    c = _rec("spiderweb-pr", "C", xid="OTHER")
    links = correlate_by_external_id([a, b, c])
    pairs = {(l["source_record_id"], l["target_record_id"]) for l in links}
    assert ("A", "B") in pairs
    assert ("A", "C") not in pairs
    assert all(l["link_type"] == "entity_correlation" and l["match_basis"].startswith("external_id") for l in links)


def test_record_point_and_external_ids_helpers():
    assert record_point({"geometry": {"type": "Point", "coordinates": [-66.0, 18.4]}}) == (18.4, -66.0)
    assert record_point({"location": {"latitude": 18.4, "longitude": -66.0}}) == (18.4, -66.0)
    assert record_point({}) is None
    assert ("uei", "X1") in record_external_ids({"entities": [{"external_ids": {"uei": "X1"}}]})
