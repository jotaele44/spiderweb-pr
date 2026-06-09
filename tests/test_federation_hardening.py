"""Theme 9 — federation hardening tests (T9-74/75/78/79)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from federation.envelope import CONTRACT_VERSION, ENVELOPE_FIELDS, EvidenceEnvelope
from federation.hub.package_loader import load_package
from federation.hub.query import correlate_by_external_id
from tests._federation_fixtures import ACME_UEI, write_both

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "fixtures" / "envelope_v1_0.golden.json"


# ── T9-74 contract version + golden envelope ─────────────────────────────────

def test_contract_version_is_pinned():
    """The golden fixture pins the contract version; envelope.py must match it."""
    golden = json.loads(GOLDEN.read_text())
    assert CONTRACT_VERSION == golden["contract_version"] == "1.0"


def test_golden_envelope_roundtrips_and_has_all_fields():
    golden = json.loads(GOLDEN.read_text())
    env = EvidenceEnvelope.from_dict(golden["envelope"])
    d = env.to_dict()
    # Every canonical field is present after a round-trip.
    for fld in ENVELOPE_FIELDS:
        assert fld in d, f"golden envelope missing field after round-trip: {fld}"
    # Round-trip is stable on the canonical fields.
    assert EvidenceEnvelope.from_dict(d).to_dict() == d


# ── T9-78 cross-producer external-id correlation ─────────────────────────────

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


# ── T9-79 federation export dry-run + diff ───────────────────────────────────

# ── T9-75 live-execution readiness criteria ──────────────────────────────────

def test_live_execution_blocked_on_synthetic_and_missing_correlations():
    from federation.readiness import evaluate_live_execution_readiness

    verdict = evaluate_live_execution_readiness(
        has_synthetic_rows=True, validated_correlations=["temporal"]
    )
    assert verdict["ready"] is False
    assert "synthetic_rows_present" in verdict["blockers"]
    assert any(b.startswith("correlations_unvalidated:") for b in verdict["blockers"])


def test_live_execution_ready_when_all_criteria_met():
    from federation.readiness import REQUIRED_CORRELATIONS, evaluate_live_execution_readiness

    verdict = evaluate_live_execution_readiness(
        has_synthetic_rows=False,
        validated_correlations=list(REQUIRED_CORRELATIONS),
    )
    assert verdict["ready"] is True
    assert verdict["blockers"] == []


def test_current_manifest_flag_matches_criteria():
    """federation.json keeps live-execution false — and the criteria agree, since
    the shipped package is synthetic / diagnostic."""
    from federation.readiness import evaluate_live_execution_readiness

    manifest = json.loads((REPO / "federation.json").read_text())
    gate = manifest["federation_readiness_gate"]
    assert gate["ready_for_hub_live_execution"] is False
    # With synthetic diagnostic data, the criteria must also say "not ready".
    verdict = evaluate_live_execution_readiness(
        has_synthetic_rows=True, validated_correlations=[]
    )
    assert verdict["ready"] is False


@pytest.fixture
def sample_pkg(tmp_path):
    """A minimal envelope package the exporter can read."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "sources.jsonl").write_text(
        json.dumps({"source_id": "src_a", "kind": "fr24", "confidence": 1.0}) + "\n"
    )
    (pkg / "airspace_events.jsonl").write_text(
        json.dumps({
            "id": "evt_0001", "source_id": "src_a",
            "observed_at": "2026-06-09T00:00:00Z", "confidence": 0.8,
            "geometry": {"type": "Point", "coordinates": [-66.1, 18.4]},
            "subject_id": "N12345",
        }) + "\n"
    )
    return pkg


def test_export_dry_run_writes_nothing(sample_pkg, tmp_path, capsys, monkeypatch):
    import scripts.federation_export as fx

    out = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        ["federation_export.py", "--package", str(sample_pkg),
         "--out", str(out), "--dry-run"],
    )
    rc = fx.main()
    assert rc == 0
    assert not out.exists(), "dry-run must not create the output dir"
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert "manifest.json" in report["would_write"]


def test_export_diff_reports_added_rows(sample_pkg, tmp_path):
    import scripts.federation_export as fx

    now = "2026-06-09T00:00:00Z"
    sources_in = fx._read_stream(sample_pkg, "sources")
    records = {n: fx._read_stream(sample_pkg, n) for n in fx.RECORD_STREAMS}
    streams = fx.build_streams(sources_in, records, now)

    # Diff against an empty previous export → everything is "added".
    diff = fx.diff_streams(streams, {"sources": [], "entities": [], "relationships": []})
    assert diff["entities"]["added"] >= 1
    assert diff["entities"]["removed"] == 0
    # Diff against itself → no changes.
    same = fx.diff_streams(streams, streams)
    assert all(v["added"] == 0 and v["removed"] == 0 and v["changed"] == 0
               for v in same.values())
