from __future__ import annotations

import hashlib
import json

import pytest

from spiderweb.place_resolver import (
    PlaceResolverError,
    bind_candidate_to_location_query,
    build_place_discovery_plan,
    parse_place_candidates,
)


def test_place_plan_is_discovery_only_and_pr_bounded() -> None:
    plan = build_place_discovery_plan({"query_id": "hucar", "text": "Hacienda Hucar", "limit": 5})
    assert plan["providers"][0]["route_state"] == "DISCOVERY_ONLY"
    assert plan["policy"]["automatic_candidate_selection"] is False
    assert "countrycodes=pr" in plan["requests"][0]["url"]


def test_candidate_parser_preserves_multiple_candidates_without_selection() -> None:
    raw = json.dumps([
        {"place_id": 1, "lat": "18.0", "lon": "-66.2", "display_name": "A", "boundingbox": ["17.9", "18.1", "-66.3", "-66.1"]},
        {"place_id": 2, "lat": "18.1", "lon": "-66.1", "display_name": "B", "boundingbox": ["18.0", "18.2", "-66.2", "-66.0"]},
    ]).encode()
    receipt = {
        "provider_id": "OSM_NOMINATIM_GEOCODER",
        "request_role": "place_search",
        "state": "PASS",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    out = parse_place_candidates(raw, receipt)
    assert out["candidate_count"] == 2
    assert out["identity_state"] == "UNRESOLVED"
    assert all(row["state"] == "CANDIDATE_NOT_IDENTITY" for row in out["candidates"])


def test_explicit_candidate_binding_creates_bounded_location_query() -> None:
    candidates = {
        "candidates": [{
            "candidate_index": 0,
            "display_name_raw": "A",
            "lat": 18.0,
            "lon": -66.2,
            "bbox": {"west": -66.3, "south": 17.9, "east": -66.1, "north": 18.1},
        }]
    }
    query = bind_candidate_to_location_query(candidates=candidates, candidate_index=0, query_id="a")
    assert query["geometry"]["type"] == "bbox"
    assert query["binding"]["binding_state"] == "ANALYST_EXPLICIT_SELECTION"


def test_nonunique_or_missing_candidate_index_fails_closed() -> None:
    with pytest.raises(PlaceResolverError):
        bind_candidate_to_location_query(candidates={"candidates": []}, candidate_index=0, query_id="x")
