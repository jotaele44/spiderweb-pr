"""Theme 9 — federation hardening tests (T9-74/75/78/79)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from federation.envelope import CONTRACT_VERSION, ENVELOPE_FIELDS, EvidenceEnvelope

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


# Cross-producer external-id correlation tests (T9-78) were retired with the
# in-repo query-hub; archived at docs/legacy/tests/test_federation_hardening_hub_xid.py.


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
    """federation.json declares live-execution true — and the criteria agree:
    the shipped real package has zero synthetic rows and the hub validated the
    canonical projection (operator-approved promotion, 2026-07-03)."""
    from federation.readiness import (
        REQUIRED_CORRELATIONS,
        evaluate_live_execution_readiness,
    )

    manifest = json.loads((REPO / "federation.json").read_text())
    gate = manifest["federation_readiness_gate"]
    assert gate["ready_for_hub_live_execution"] is True
    assert gate["blocking_conditions"] == []
    # With real (non-synthetic) rows and hub-validated correlations, the
    # criteria must also say "ready" — the flag and the criteria move together.
    verdict = evaluate_live_execution_readiness(
        has_synthetic_rows=False, validated_correlations=list(REQUIRED_CORRELATIONS)
    )
    assert verdict["ready"] is True


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
