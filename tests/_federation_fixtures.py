"""Synthetic federation fixtures for the spiderweb-pr hub tests.

Not a test module (no ``test_`` prefix). Builds two on-disk export packages:

* a spiderweb airspace package (this repo's producer output), and
* a contract-sweeper funding package (the OTHER producer's output, simulated as
  raw envelope dicts — the hub only ever reads JSONL, never imports CS code).

The two packages share anchors so the hub produces links:
  * entity: operator "ACME CONSTRUCTION INC" -> normalized "ACME CONSTRUCTION"
  * time:   airspace event 2023-03-20 within 7 days of award 2023-03-15
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from federation.envelope import EvidenceEnvelope, entity_ref
from federation.export_writer import (
    build_airspace_event,
    normalize_name,
    org_entity_ref,
    write_package,
)
from federation.namespace import namespaced_id

CS_PREFIX = "contract_sweeper"
CS_PRODUCER = "contract-sweeper"
CS_RECORD_TYPES = {
    "funding_awards": "funding_award",
    "transactions": "transaction",
    "entities": "entity",
    "relationships": "relationship",
    "sources": "source",
}


# --------------------------------------------------------------------------
# spiderweb airspace producer streams
# --------------------------------------------------------------------------


# Shared external id carried by ACME in BOTH producers — lets the hub correlate
# them on a stable government identifier (UEI) independent of name spelling (T9-78).
ACME_UEI = "ACME123UEI4567"


def build_spiderweb_streams(*, synthetic: bool = True) -> Dict[str, List[EvidenceEnvelope]]:
    acme = org_entity_ref("op_acme", "ACME CONSTRUCTION INC")
    acme["external_ids"] = {"uei": ACME_UEI}
    src_fr24 = "src_fr24"

    event = build_airspace_event(
        "event_abc123",
        source_id=src_fr24,
        event_time="2023-03-20T00:00:00Z",
        lat=18.4655,
        lon=-66.1057,
        entities=[acme],
        confidence_score=0.82,
        synthetic=synthetic,
        payload={"callsign": "N5854Z", "mission_type": "INFRASTRUCTURE_SURVEY"},
    )

    observation = EvidenceEnvelope(
        producer="spiderweb-pr",
        record_type="observation",
        record_id=namespaced_id("obs_001"),
        source_id=namespaced_id(src_fr24),
        timestamp="2023-03-21T00:00:00Z",
        geo={"type": "Point", "coordinates": [-66.1057, 18.4655]},
        entities=[acme],
        confidence={"score": 0.70, "method": "producer_contract"},
        lineage=[{"stage": "ocr_fusion"}],
        payload={"raw_text": "ACME survey rotorcraft over San Juan"},
        synthetic=synthetic,
    )

    track = EvidenceEnvelope(
        producer="spiderweb-pr",
        record_type="track",
        record_id=namespaced_id("track_001"),
        source_id=namespaced_id(src_fr24),
        timestamp="2023-03-20T00:00:00Z",
        geo={"type": "LineString", "coordinates": [[-66.1057, 18.4655], [-66.50, 18.00]]},
        confidence={"score": 0.60, "method": "producer_contract"},
        lineage=[{"stage": "route_extractor"}],
        payload={"points": 5},
        synthetic=synthetic,
    )

    source = EvidenceEnvelope(
        producer="spiderweb-pr",
        record_type="source",
        record_id=namespaced_id(src_fr24),
        source_id=namespaced_id(src_fr24),
        timestamp="2023-03-01T00:00:00Z",
        confidence={"score": 1.0, "method": "producer_contract"},
        lineage=[{"stage": "screenshot_inventory"}],
        payload={"name": "FlightRadar24 screenshots"},
        synthetic=synthetic,
    )

    return {
        "airspace_events": [event],
        "observations": [observation],
        "tracks": [track],
        "sources": [source],
    }


# --------------------------------------------------------------------------
# contract-sweeper funding producer streams (simulated other producer)
# --------------------------------------------------------------------------


def _cs_id(raw: str) -> str:
    return namespaced_id(raw, prefix=CS_PREFIX)


def _cs_entity(raw_id: str, name: str, synthetic: bool) -> EvidenceEnvelope:
    nid = _cs_id(raw_id)
    return EvidenceEnvelope(
        producer=CS_PRODUCER,
        record_type="entity",
        record_id=nid,
        source_id=_cs_id("src_usaspending"),
        entities=[entity_ref(nid, name, normalize_name(name))],
        confidence={"score": 1.0, "method": "producer_contract"},
        lineage=[{"stage": "entity_resolution"}],
        synthetic=synthetic,
    )


def build_contract_sweeper_streams(*, synthetic: bool = True) -> Dict[str, List[EvidenceEnvelope]]:
    src = "src_usaspending"
    acme = _cs_entity("ent_acme", "ACME CONSTRUCTION INC", synthetic)
    navy = _cs_entity("ent_navy", "Department of the Navy", synthetic)
    acme_ref = acme.entities[0]
    acme_ref["external_ids"] = {"uei": ACME_UEI}  # same UEI as the spiderweb ACME (T9-78)
    navy_ref = navy.entities[0]

    award = EvidenceEnvelope(
        producer=CS_PRODUCER,
        record_type="funding_award",
        record_id=_cs_id("award_abc123"),
        source_id=_cs_id(src),
        timestamp="2023-03-15T00:00:00Z",
        entities=[acme_ref, navy_ref],
        confidence={"score": 0.91, "method": "producer_contract"},
        lineage=[{"stage": "award_ingest"}],
        payload={"amount": 1234567.89, "currency": "USD", "piid": "W911NF20C0001"},
        synthetic=synthetic,
    )

    transaction = EvidenceEnvelope(
        producer=CS_PRODUCER,
        record_type="transaction",
        record_id=_cs_id("txn_001"),
        source_id=_cs_id(src),
        timestamp="2023-03-18T00:00:00Z",
        entities=[acme_ref],
        confidence={"score": 0.88, "method": "producer_contract"},
        lineage=[{"stage": "transaction_ingest"}],
        payload={"amount": 500000.0, "currency": "USD"},
        synthetic=synthetic,
    )

    relationship = EvidenceEnvelope(
        producer=CS_PRODUCER,
        record_type="relationship",
        record_id=_cs_id("rel_001"),
        source_id=_cs_id(src),
        timestamp="2023-03-15T00:00:00Z",
        entities=[acme_ref, navy_ref],
        confidence={"score": 0.90, "method": "producer_contract"},
        lineage=[{"stage": "relationship_resolution"}],
        payload={"relationship_type": "awarded_by"},
        synthetic=synthetic,
    )

    source = EvidenceEnvelope(
        producer=CS_PRODUCER,
        record_type="source",
        record_id=_cs_id(src),
        source_id=_cs_id(src),
        timestamp="2023-03-01T00:00:00Z",
        confidence={"score": 1.0, "method": "producer_contract"},
        lineage=[{"stage": "source_registry"}],
        payload={"name": "USAspending.gov"},
        synthetic=synthetic,
    )

    return {
        "funding_awards": [award],
        "transactions": [transaction],
        "entities": [acme, navy],
        "relationships": [relationship],
        "sources": [source],
    }


# --------------------------------------------------------------------------
# Package writers
# --------------------------------------------------------------------------


def write_spiderweb_package(out_dir, *, synthetic: bool = True) -> Dict[str, Any]:
    return write_package(out_dir, build_spiderweb_streams(synthetic=synthetic), synthetic=synthetic)


def write_contract_sweeper_package(out_dir, *, synthetic: bool = True) -> Dict[str, Any]:
    return write_package(
        out_dir,
        build_contract_sweeper_streams(synthetic=synthetic),
        synthetic=synthetic,
        producer=CS_PRODUCER,
        prefix=CS_PREFIX,
        record_types=CS_RECORD_TYPES,
    )


def write_both(base_dir, *, synthetic: bool = True):
    base = Path(base_dir)
    sw = base / "spiderweb_airspace_export"
    cs = base / "contract_sweeper_export"
    write_spiderweb_package(sw, synthetic=synthetic)
    write_contract_sweeper_package(cs, synthetic=synthetic)
    return sw, cs
