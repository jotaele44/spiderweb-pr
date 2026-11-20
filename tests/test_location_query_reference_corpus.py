from __future__ import annotations

import json
from pathlib import Path

from spiderweb.location_query import load_registry
from spiderweb.reference_corpus import build_reference_corpus


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_reference_corpus_closes_three_aois_without_network() -> None:
    references = json.loads(
        (ROOT / "configs/location_query_reference_aois.json").read_text(encoding="utf-8")
    )
    registry = load_registry(ROOT / "configs/location_query_providers.json")
    out = build_reference_corpus(references, registry=registry, env={})
    assert out["state"] == "PASS"
    assert out["reference_aoi_count"] == 3
    assert out["reference_aoi_ids"] == ["hucar_2km", "san_juan_metro_bbox", "boqueron_bbox"]
    assert out["network_requests"] == 0
    assert out["invariants"]["row_conservation"] is True
    assert out["invariants"]["all_plan_mode"] is True
    assert out["invariants"]["all_fetch_gate_not_requested"] is True
    assert out["invariants"]["all_provider_registry_hashes_equal"] is True
    assert all(item["provider_denominator_count"] > 0 for item in out["plans"])
    assert all(item["request_count"] > 0 for item in out["plans"])


def test_every_reference_plan_binds_same_registry_hash() -> None:
    references = json.loads(
        (ROOT / "configs/location_query_reference_aois.json").read_text(encoding="utf-8")
    )
    registry = load_registry(ROOT / "configs/location_query_providers.json")
    out = build_reference_corpus(references, registry=registry, env={})
    expected = out["provider_registry_sha256"]
    assert isinstance(expected, str) and len(expected) == 64
    assert all(
        item["plan"]["provider_registry_sha256"] == expected
        for item in out["plans"]
    )
