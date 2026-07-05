"""Cross-repo hub query tests: load -> validate -> index -> correlate."""
from __future__ import annotations

import pytest

from federation.hub.package_loader import load_package
from federation.hub.query import (
    correlate_entities,
    correlate_temporal,
    filter_by_confidence,
    query_federation,
)
from tests._federation_fixtures import write_both


@pytest.fixture
def packages(tmp_path):
    sw, cs = write_both(tmp_path, synthetic=True)
    return [str(sw), str(cs)]


def _all_records(packages):
    records = []
    for pkg in packages:
        records.extend(load_package(pkg)["records"])
    return records


def test_load_packages_clean(packages):
    for pkg in packages:
        loaded = load_package(pkg)
        assert loaded["errors"] == []
        assert loaded["records"]


def test_both_packages_validate(packages):
    result = query_federation("all records", packages, mode="test")
    assert result["validation"] == {"spiderweb-pr": "PASS", "moneysweep-pr": "PASS"}


def test_missing_manifest_fails_closed(tmp_path, packages):
    bogus = tmp_path / "empty_pkg"
    bogus.mkdir()
    result = query_federation("x", [packages[0], str(bogus)], mode="test")
    assert result["records"] == []
    assert result["links"] == []
    assert "FAIL" in result["validation"].values()


def test_mode_a_time_window_correlation(packages):
    records = _all_records(packages)
    links = correlate_temporal(records, window_days=7)
    assert links, "award (03-15) and airspace event (03-20) are within 7 days"
    assert all(link["link_type"] == "temporal_proximity" for link in links)
    # All links must be cross-producer pairs.
    for link in links:
        assert link["source_record_id"].split(":")[0] != link["target_record_id"].split(":")[0]
    # Narrowing the window to 1 day drops the 5-day-apart award/event pairing.
    assert len(correlate_temporal(records, window_days=1)) < len(links)


def test_mode_b_entity_correlation(packages):
    records = _all_records(packages)
    links = correlate_entities(records)
    assert links, "ACME CONSTRUCTION appears in both producers"
    acme_links = [l for l in links if "ACME CONSTRUCTION" in l["explanation"]]
    assert acme_links
    assert all(l["match_basis"] == "normalized_name" for l in acme_links)


def test_mode_c_confidence_filter(packages):
    records = _all_records(packages)
    low = filter_by_confidence(records, 0.75)
    assert low, "track (0.60) and observation (0.70) are below 0.75"
    assert all(rec["confidence"]["score"] < 0.75 for rec in low)


def test_mode_d_evidence_bundle_acme_march_2023(packages):
    result = query_federation(
        "records related to ACME in March 2023", packages, mode="test"
    )
    assert result["validation"] == {"spiderweb-pr": "PASS", "moneysweep-pr": "PASS"}
    assert result["records"], "ACME records exist in March 2023"
    assert all("entity" in r["matched_on"] for r in result["records"])
    assert all("time_window" in r["matched_on"] for r in result["records"])
    # Cross-producer links of both kinds should surface.
    link_types = {l["link_type"] for l in result["links"]}
    assert "temporal_proximity" in link_types
    assert "entity_correlation" in link_types


def test_production_mode_rejects_synthetic_packages(tmp_path):
    sw, cs = write_both(tmp_path, synthetic=True)
    result = query_federation("all", [str(sw), str(cs)], mode="production")
    assert result["records"] == []
    assert set(result["validation"].values()) == {"FAIL"}


def test_entity_collision_keeps_both_record_ids(tmp_path):
    # Two distinct producer records sharing a normalized name must both appear
    # in the entity link's endpoints (expected fan-out, not a merge).
    sw, cs = write_both(tmp_path, synthetic=True)
    records = _all_records([str(sw), str(cs)])
    links = correlate_entities(records)
    pairs = {(l["source_record_id"], l["target_record_id"]) for l in links}
    # The spiderweb airspace event and the CS award both name ACME.
    assert any(
        "spiderweb:event_abc123" in pair and "moneysweep:award_abc123" in pair
        for pair in pairs
    )
