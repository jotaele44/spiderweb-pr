"""The demo seed must speak the PRIIS vocabulary the UI validates against.

`server/frontend/src/schemas/priis.ts` validates every API response with Zod and
`parseArray` drops non-conforming rows *silently*. The demo seed had drifted onto
its own vocabulary (`status="active"`, `band="high"`, `procurement_method="open"`,
`kind="adsb"`), so in live mode the frontend discarded every contract, anomaly and
source while the header still read "LIVE" — the modules looked empty rather than
broken, and nothing logged outside a dev build.

The seed also stored agency and vendor *names* in what are foreign-key columns.
The UI resolves those with `byId()`, so the contract pane's "Agency ·" and
"Vendor ·" links silently did not render.

These tests pin both contracts. The enums are duplicated here deliberately: this
is a cross-language boundary, and the point is to fail when the two sides drift.
Update them together with `schemas/priis.ts` and `types/priis.ts`.
"""
from __future__ import annotations

import pytest

from server.ingestion import seed_demo

CONTRACT_STATUS = {"planned", "executed", "amended", "flagged", "closed", "unknown"}
PROCUREMENT_METHOD = {"competitive", "sole_source", "emergency", "amendment", "unknown"}
EVIDENCE_TIER = {"T1", "T2", "T3", "T4"}
ANOMALY_CATEGORY = {
    "financial", "spatial", "temporal", "infrastructure", "imagery", "report", "cross-domain",
}
ANOMALY_BAND = {"lo", "md", "hi"}
ANOMALY_FACTOR_TAG = {"finance", "spatial", "temporal", "infra", "report", "imagery", "source"}
EVENT_KIND = {
    "contract", "imagery", "report", "outage", "permit", "field", "filing", "sighting", "other",
}
SOURCE_KIND = {"technical", "operational", "eyewitness", "secondary", "derived"}
SOURCE_STATUS = {"online", "partial", "offline"}
INVESTIGATION_STATUS = {"active", "paused", "closed", "needs_review"}
ALERT_KIND = {"finance", "spatial", "source", "anomaly", "report"}


@pytest.mark.parametrize("row", seed_demo.CONTRACTS, ids=lambda r: r[0])
def test_contract_enums(row):
    _id, _agency, _vendor, _site, _amount, _signed, status, tier, procurement = row[:9]
    assert status in CONTRACT_STATUS, f"{_id}: contract status {status!r}"
    assert tier in EVIDENCE_TIER, f"{_id}: tier {tier!r}"
    assert procurement in PROCUREMENT_METHOD, f"{_id}: procurement_method {procurement!r}"


@pytest.mark.parametrize("row", seed_demo.ANOMALIES, ids=lambda r: r[0])
def test_anomaly_enums(row):
    _id, _title, category, _score, band = row[:5]
    factors = row[7]
    assert category in ANOMALY_CATEGORY, f"{_id}: category {category!r}"
    assert band in ANOMALY_BAND, f"{_id}: band {band!r}"
    for factor in factors:
        assert factor["tag"] in ANOMALY_FACTOR_TAG, f"{_id}: factor tag {factor['tag']!r}"


@pytest.mark.parametrize("row", seed_demo.EVENTS, ids=lambda r: r[0])
def test_event_enums(row):
    assert row[1] in EVENT_KIND, f"{row[0]}: event kind {row[1]!r}"


@pytest.mark.parametrize("row", seed_demo.SOURCES, ids=lambda r: r[0])
def test_source_enums(row):
    _id, _name, tier, kind, status = row
    assert tier in EVIDENCE_TIER, f"{_id}: tier {tier!r}"
    assert kind in SOURCE_KIND, f"{_id}: source kind {kind!r}"
    assert status in SOURCE_STATUS, f"{_id}: source status {status!r}"


@pytest.mark.parametrize("row", seed_demo.INVESTIGATIONS, ids=lambda r: r[0])
def test_investigation_enums(row):
    assert row[3] in INVESTIGATION_STATUS, f"{row[0]}: investigation status {row[3]!r}"


@pytest.mark.parametrize("row", seed_demo.ALERTS, ids=lambda r: r[0])
def test_alert_enums(row):
    assert row[2] in ALERT_KIND, f"{row[0]}: alert kind {row[2]!r}"
    assert row[4] in EVIDENCE_TIER, f"{row[0]}: tier {row[4]!r}"


def test_contract_foreign_keys_are_ids_not_names():
    agencies = {row[0] for row in seed_demo.AGENCIES}
    vendors = {row[0] for row in seed_demo.VENDORS}
    sites = {row[0] for row in seed_demo.SITES}
    for row in seed_demo.CONTRACTS:
        cid, agency, vendor, site = row[0], row[1], row[2], row[3]
        assert agency in agencies, f"{cid}: agency {agency!r} is not an agency id"
        assert vendor in vendors, f"{cid}: vendor {vendor!r} is not a vendor id"
        assert site is None or site in sites, f"{cid}: site {site!r} is not a site id"


def test_anomaly_and_event_references_resolve():
    contracts = {row[0] for row in seed_demo.CONTRACTS}
    events = {row[0] for row in seed_demo.EVENTS}
    sites = {row[0] for row in seed_demo.SITES}
    investigations = {row[0] for row in seed_demo.INVESTIGATIONS}

    for row in seed_demo.ANOMALIES:
        aid, site_id = row[0], row[5]
        assert site_id is None or site_id in sites, f"{aid}: siteId {site_id!r}"
        for ref in row[8]:
            assert ref in contracts, f"{aid}: contract ref {ref!r}"
        for ref in row[9]:
            assert ref in events, f"{aid}: event ref {ref!r}"

    for row in seed_demo.EVENTS:
        eid, site_id, ref_id = row[0], row[3], row[4]
        assert site_id in sites, f"{eid}: siteId {site_id!r}"
        assert ref_id is None or ref_id in contracts, f"{eid}: refId {ref_id!r}"

    for row in seed_demo.ALERTS:
        assert row[5] is None or row[5] in investigations, f"{row[0]}: investigation {row[5]!r}"


def test_high_confidence_anomalies_have_t1_or_t2_evidence():
    contract_tiers = {row[0]: row[7] for row in seed_demo.CONTRACTS}
    event_tiers = {row[0]: row[6] for row in seed_demo.EVENTS}

    for row in seed_demo.ANOMALIES:
        anomaly_id, contract_ids, event_ids, confidence = (
            row[0], row[8], row[9], row[10]
        )
        if confidence != 3:
            continue
        tiers = {contract_tiers[ref] for ref in contract_ids}
        tiers.update(event_tiers[ref] for ref in event_ids)
        assert tiers & {"T1", "T2"}, (
            f"{anomaly_id}: confidence 3 has only {sorted(tiers)} evidence"
        )


def test_seed_carries_no_retired_airspace_vocabulary():
    """The FR24/ADS-B surface was ceded to skywatcher-pr in fcb658b."""
    blob = repr(seed_demo.SOURCES) + repr(seed_demo.EVENTS) + repr(seed_demo.ANOMALIES)
    for term in ("adsb", "ADS-B", "fr24", "FR24", "flight", "aircraft"):
        assert term not in blob, f"retired airspace term {term!r} still in the demo seed"
