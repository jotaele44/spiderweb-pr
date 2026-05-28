"""Envelope + namespacing contract tests for the spiderweb-pr producer."""
from __future__ import annotations

import pytest

from federation.envelope import EvidenceEnvelope, entity_ref
from federation.export_writer import normalize_name
from federation.namespace import (
    PREFIX,
    is_namespaced,
    namespaced_id,
    prefix_for_producer,
)


def test_namespaced_id_prefixes_raw():
    assert namespaced_id("event_abc") == "spiderweb:event_abc"


def test_namespaced_id_is_idempotent():
    once = namespaced_id("src_fr24")
    assert namespaced_id(once) == once
    assert is_namespaced(once)


def test_namespaced_id_supports_other_prefix():
    cs = namespaced_id("award_1", prefix="contract_sweeper")
    assert cs == "contract_sweeper:award_1"
    assert namespaced_id(cs, prefix="contract_sweeper") == cs


def test_namespaced_id_rejects_empty():
    with pytest.raises(ValueError):
        namespaced_id("")
    with pytest.raises(ValueError):
        namespaced_id(None)


def test_prefix_for_producer():
    assert prefix_for_producer("spiderweb-pr") == "spiderweb"
    assert prefix_for_producer("contract-sweeper") == "contract_sweeper"
    assert prefix_for_producer("unknown") is None


def test_normalize_name_strips_legal_suffix():
    # Must match the funding producer's normalization so entities join.
    assert normalize_name("ACME CONSTRUCTION INC") == "ACME CONSTRUCTION"


def test_envelope_round_trips_through_dict():
    env = EvidenceEnvelope(
        producer=PREFIX,
        record_type="airspace_event",
        record_id=namespaced_id("event_abc"),
        source_id=namespaced_id("src_fr24"),
        entities=[entity_ref(namespaced_id("op_acme"), "ACME", "ACME")],
    )
    d = env.to_dict()
    assert set(d) == {
        "producer", "record_type", "record_id", "source_id", "timestamp",
        "geo", "entities", "confidence", "lineage", "payload", "synthetic",
    }
    assert EvidenceEnvelope.from_dict(d).to_dict() == d
