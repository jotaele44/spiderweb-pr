"""Spiderweb maintenance layer: detection, adapter, corrections, runner.

Thorough by design — the maintenance package is vendored, and exercising its
branches keeps it well-covered under the repo's coverage gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance import REPORT_RELPATH, detect, run_maintenance  # noqa: E402
from maintenance import state as state_mod  # noqa: E402
from maintenance.adapters import local  # noqa: E402


def _federation(root, **outputs):
    fed = {"program_id": "spiderweb-pr", "canonical_outputs": outputs}
    (root / "federation.json").write_text(json.dumps(fed), encoding="utf-8")
    return state_mod.collect_repo_state(root)


def _write_samples(root, *, manifest="{}", streams=None):
    d = root / "exports" / "samples"
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.sample.json").write_text(manifest, encoding="utf-8")
    for name, rows in (streams or {}).items():
        (d / name).write_text("\n".join(rows) + "\n", encoding="utf-8")


# ---- detection ----


def test_missing_federation_json_is_critical(tmp_path):
    state = state_mod.collect_repo_state(tmp_path)
    findings = detect.detect_missing_required_files("spiderweb-pr", tmp_path, state)
    assert any(f.category == "manifest" and f.severity == "critical" for f in findings)


def test_invalid_json_output_is_error(tmp_path):
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "x.json").write_text("{nope", encoding="utf-8")
    state = _federation(tmp_path, x="exports/x.json")
    findings = detect.detect_invalid_json("spiderweb-pr", tmp_path, state)
    assert any(f.category == "schema" and f.severity == "error" for f in findings)


def test_duplicate_jsonl_detected(tmp_path):
    d = tmp_path / "exports" / "federation"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text('{"a":1}\n{"a":1}\n{"a":2}\n', encoding="utf-8")
    state = _federation(tmp_path, canonical_export_dir="exports/federation")
    findings = detect.detect_exact_duplicate_jsonl("spiderweb-pr", tmp_path, state)
    assert len(findings) == 1
    assert findings[0].category == "duplicate"


# ---- adapter: migration remnants ----


def test_no_fr24_remnants_passes(tmp_path):
    state = _federation(tmp_path)
    assert local.check_migration_remnants("spiderweb-pr", tmp_path, state) == []


def test_fr24_dir_is_warning(tmp_path):
    (tmp_path / "fr24").mkdir()
    state = _federation(tmp_path)
    findings = local.check_migration_remnants("spiderweb-pr", tmp_path, state)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


# ---- adapter: GIS artifact integrity ----


def test_clean_samples_pass(tmp_path):
    _write_samples(
        tmp_path,
        manifest='{"files": []}',
        streams={"events.sample.jsonl": ['{"id": 1}', '{"id": 2}']},
    )
    state = _federation(tmp_path)
    assert local.check_gis_artifact_integrity("spiderweb-pr", tmp_path, state) == []


def test_bad_manifest_is_error(tmp_path):
    _write_samples(tmp_path, manifest="{not json")
    state = _federation(tmp_path)
    findings = local.check_gis_artifact_integrity("spiderweb-pr", tmp_path, state)
    assert any(
        f.category == "export_integrity" and f.severity == "error" for f in findings
    )


def test_bad_jsonl_row_is_error(tmp_path):
    _write_samples(
        tmp_path,
        manifest="{}",
        streams={"events.sample.jsonl": ['{"id": 1}', "{broken"]},
    )
    state = _federation(tmp_path)
    findings = local.check_gis_artifact_integrity("spiderweb-pr", tmp_path, state)
    assert any("unparseable" in f.message for f in findings)


# ---- corrections + runner (write path) ----


def test_audit_does_not_mutate_but_safe_correct_does(tmp_path):
    d = tmp_path / "exports" / "federation"
    d.mkdir(parents=True)
    jsonl = d / "events.jsonl"
    jsonl.write_text('{"a":1}\n{"a":1}\n{"a":2}\n', encoding="utf-8")
    _federation(tmp_path, canonical_export_dir="exports/federation")

    before = jsonl.read_text(encoding="utf-8")
    audit = run_maintenance(root=tmp_path, mode="audit", write=False)
    assert any(f.category == "duplicate" and f.action == "none" for f in audit.findings)
    assert jsonl.read_text(encoding="utf-8") == before

    fixed = run_maintenance(root=tmp_path, mode="safe-correct", write=False)
    assert any(f.action == "auto_corrected" for f in fixed.findings)
    lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_run_maintenance_writes_report_and_review_queue(tmp_path):
    _write_samples(
        tmp_path, manifest="{not json"
    )  # produces an error finding -> review queue
    _federation(tmp_path, export_sample_manifest="exports/samples/manifest.sample.json")
    report = run_maintenance(root=tmp_path, mode="audit", write=True)
    assert (tmp_path / REPORT_RELPATH).exists()
    assert (tmp_path / "reports" / "maintenance" / "review_queue.json").exists()
    assert report.promotion_blocked is False  # errors are quarantined, not critical
