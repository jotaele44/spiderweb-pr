"""QUARANTINED — former cross-producer external-id correlation tests (T9-78).

Carved out of tests/test_federation_hardening.py when spiderweb-pr became a
producer-only federation node and the in-repo query-hub was retired to
docs/legacy/federation/hub/. Kept as design history; NOT collected by pytest
(docs/ is outside testpaths). See docs/REPO_BOUNDARY.md.
"""
from __future__ import annotations

from federation.hub.package_loader import load_package
from federation.hub.query import correlate_by_external_id
from tests._federation_fixtures import ACME_UEI, write_both


def test_external_id_correlation_links_cross_producer(tmp_path):
    sw, cs = write_both(tmp_path, synthetic=True)
    records = []
    for pkg in (str(sw), str(cs)):
        records.extend(load_package(pkg)["records"])

    links = correlate_by_external_id(records)
    assert links, "ACME shares a UEI across both producers — expected a link"
    for link in links:
        assert link["match_basis"] == "external_id:uei"
        # Endpoints must be cross-producer (different namespace prefixes).
        a = link["source_record_id"].split(":")[0]
        b = link["target_record_id"].split(":")[0]
        assert a != b, f"external-id link must be cross-producer: {link}"


def test_external_id_value_carried_in_fixtures(tmp_path):
    sw, _ = write_both(tmp_path, synthetic=True)
    records = load_package(str(sw))["records"]
    seen = {
        val
        for rec in records
        for ent in (rec.get("entities") or [])
        for val in (ent.get("external_ids") or {}).values()
    }
    assert ACME_UEI in seen


def test_external_id_no_links_when_unique():
    """Records with distinct external ids produce no links."""
    recs = [
        {"producer": "a", "record_id": "a:1",
         "entities": [{"external_ids": {"uei": "AAA"}}]},
        {"producer": "b", "record_id": "b:1",
         "entities": [{"external_ids": {"uei": "BBB"}}]},
    ]
    assert correlate_by_external_id(recs) == []
