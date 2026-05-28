"""Tests for readiness/pr_intake_import.py.

Covers the cross-repo seam Contract-Sweeper -> spiderweb-pr:
  * unit tests against a hand-built spiderweb_pr_derivatives.csv that mirrors the
    producer's real on-disk shape (alphabetized columns, JSON-encoded domains,
    empty-string nulls);
  * a round-trip test that runs the real Contract-Sweeper router and feeds its
    output through the importer (skipped if the sibling repo / PyYAML is absent).
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from readiness.pr_intake_import import PRIntakeImport

CONTRACT_SWEEPER = Path(__file__).resolve().parents[2] / "Contract-Sweeper"


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _write_derivatives(d: Path, rows, filename="spiderweb_pr_derivatives.csv") -> None:
    """Write rows the same way the producer's write_csv/flatten_for_csv does:
    JSON-encode list/dict values, map None -> "", header = sorted union of keys."""
    flat = []
    for r in rows:
        fr = {}
        for k, v in r.items():
            if isinstance(v, (dict, list, tuple, set)):
                fr[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
            elif v is None:
                fr[k] = ""
            else:
                fr[k] = v
        flat.append(fr)
    fieldnames = sorted({k for fr in flat for k in fr})
    with (d / filename).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(flat)


def _row(record_id, domains, **over):
    base = {
        "record_id": record_id,
        "source_item_id": "RAW-X",
        "target_repo": "spiderweb-pr",
        "canonical_repo": "spiderweb-pr",
        "related_repo_record_id": None,
        "source_name": "USGS",
        "source_url": "https://example.test/x",
        "published_at": "2026-05-27",
        "discovered_at": "2026-05-27T12:00:00Z",
        "title": "PR spatial dataset",
        "summary_own_words": "summary",
        "domains": domains,
        "final_status": "routed_spiderweb_pr",
        "output_tables": [],
        "evidence_tier": "T2",
        "confidence_level": "High",
        "source_hash": "abc123",
        "content_hash": "def456",
        "dedupe_group_id": None,
    }
    base.update(over)
    return base


def _mixed_rows():
    return [
        _row("SW-PRINTAKE-0000000000a1", ["subsurface_hydro"]),
        _row("SW-PRINTAKE-0000000000a2", ["infrastructure_footprint", "public_funding"],
             final_status="dual_routed_contract_primary", canonical_repo="Contract-Sweeper"),
        _row("SW-PRINTAKE-0000000000a3", ["maritime_activity"],
             latitude=18.45, longitude=-66.10),          # spatial (optional cols)
        _row("NOT-A-VALID-ID", ["geography_gis"]),                       # bad: record_id fails pattern
        _row("SW-PRINTAKE-0000000000b2", []),                            # bad: empty domains array
    ]


# ── Unit: validation, zero-loss, outputs ──────────────────────────────────────

def test_imports_valid_rows_and_routes_invalid_to_review(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()

    assert manifest["record_count"] == 3
    assert manifest["review_count"] == 2
    assert manifest["candidate_count"] == 3  # mirrors record_count for manifest-schema parity


def test_zero_loss_invariant(tmp_path):
    rows = _mixed_rows()
    _write_derivatives(tmp_path, rows)
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()

    src = manifest["sources"][0]
    assert src["records_loaded"] == len(rows)
    assert src["records_valid"] + src["parse_errors"] == src["records_loaded"]
    assert manifest["zero_loss_pass"] is True


def test_records_json_preserves_provenance_and_parses_arrays(tmp_path):
    _write_derivatives(tmp_path, [_row("SW-PRINTAKE-0000000000a1", ["subsurface_hydro"])])
    PRIntakeImport(str(tmp_path), str(tmp_path)).run()

    data = json.loads((tmp_path / "pr_intake_records.json").read_text())
    assert data["record_count"] == 1
    rec = data["records"][0]
    assert rec["domains"] == ["subsurface_hydro"]          # JSON string parsed back to a list
    assert rec["output_tables"] == []
    assert rec["source_hash"] == "abc123"
    assert rec["dedupe_group_id"] == ""                    # null arrived as empty string
    assert rec["source_layer"] == "pr_intake_spiderweb_export"


def test_non_spatial_by_default_spatial_rows_emit_geojson(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()

    assert manifest["spatial_count"] == 1
    geo = json.loads((tmp_path / "pr_intake_records.geojson").read_text())
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == 1
    assert geo["features"][0]["geometry"]["coordinates"] == [-66.10, 18.45]


def test_review_queue_csv_lists_invalid_rows(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    PRIntakeImport(str(tmp_path), str(tmp_path)).run()

    with (tmp_path / "pr_intake_review_queue.csv").open(encoding="utf-8") as f:
        review = list(csv.DictReader(f))
    ids = {r["record_id"] for r in review}
    assert ids == {"NOT-A-VALID-ID", "SW-PRINTAKE-0000000000b2"}
    assert all(r["errors"] for r in review)


def test_empty_title_and_source_url_still_import(tmp_path):
    # The producer may emit empty title/source_url; the consumer must not be
    # stricter than the producer (zero-loss): such rows import as records.
    _write_derivatives(tmp_path, [_row("SW-PRINTAKE-0000000000d1", ["geography_gis"],
                                       title="", source_url="")])
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()
    assert manifest["record_count"] == 1
    assert manifest["review_count"] == 0


def test_wrong_target_repo_is_rejected(tmp_path):
    _write_derivatives(tmp_path, [_row("SW-PRINTAKE-0000000000c1", ["maritime_activity"],
                                       target_repo="Contract-Sweeper")])
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()
    assert manifest["record_count"] == 0
    assert manifest["review_count"] == 1


def test_missing_input_file_is_graceful_and_zero_loss(tmp_path):
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()
    assert manifest["record_count"] == 0
    assert manifest["missing_files"] == ["spiderweb_pr_derivatives.csv"]
    assert manifest["zero_loss_pass"] is True


def test_all_output_files_written(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    PRIntakeImport(str(tmp_path), str(tmp_path)).run()
    for name in ("pr_intake_records.json", "pr_intake_records.geojson",
                 "pr_intake_review_queue.csv", "pr_intake_import_manifest.json"):
        assert (tmp_path / name).exists(), f"missing output: {name}"


def test_status_counts_reflect_final_status(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    manifest = PRIntakeImport(str(tmp_path), str(tmp_path)).run()
    assert manifest["status_counts"].get("routed_spiderweb_pr") == 2
    assert manifest["status_counts"].get("dual_routed_contract_primary") == 1


# ── End-to-end round-trip against the real Contract-Sweeper router ────────────

@pytest.mark.skipif(
    not (CONTRACT_SWEEPER / "run_pr_intake_router.py").exists(),
    reason="Contract-Sweeper sibling repo not present",
)
def test_round_trip_zero_loss_across_the_seam(tmp_path):
    pytest.importorskip("yaml", reason="router requires PyYAML")
    fixture = CONTRACT_SWEEPER / "tests" / "fixtures" / "pr_intake_router_sample.jsonl"
    if not fixture.exists():
        pytest.skip("router sample fixture missing")

    export_dir = tmp_path / "export"
    proc = subprocess.run(
        [sys.executable, "run_pr_intake_router.py",
         "--input", str(fixture), "--out-dir", str(export_dir)],
        cwd=str(CONTRACT_SWEEPER), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"router export unavailable in this env: {proc.stderr.strip()[:300]}")

    summary = json.loads((export_dir / "routing_summary.json").read_text())
    exported = summary["spiderweb_pr_derivative_count"]
    assert exported > 0, "sample fixture should produce at least one spiderweb-pr derivative"

    manifest = PRIntakeImport(str(export_dir), str(tmp_path / "out")).run()

    # Every exported derivative is accounted for on import (zero-loss across the seam).
    assert manifest["sources"][0]["records_loaded"] == exported
    assert manifest["record_count"] + manifest["review_count"] == exported
    assert manifest["zero_loss_pass"] is True
    # Real router output conforms to the contract schema.
    assert manifest["review_count"] == 0
    assert manifest["record_count"] == exported
