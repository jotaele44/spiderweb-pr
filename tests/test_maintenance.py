"""Spiderweb maintenance adapter: repo-specific checks + shared-package wiring.

Generic detection/runner behavior now lives in thehub-pr's shared
`prii_maintenance` package (thehub-pr/packages/prii_maintenance/tests/); this
file keeps only the checks genuinely specific to spiderweb-pr
(`maintenance/adapters/local.py`) plus a smoke test proving the CLI shim's
dependency-injection wiring (`prii_maintenance.run_maintenance(...,
local_checks=local.run_checks)`) actually invokes this repo's adapter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prii_maintenance import run_maintenance  # noqa: E402
from prii_maintenance import state as state_mod  # noqa: E402

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


# The 2026-07 audit found airspace remnants in the dashboard UI, server/ingestion,
# scripts/*adsb* and the RLSM schemas/configs while this check was green, because
# it only looked at fr24/ and {pipeline,scripts}/fr24_*.py. Each case below is one
# of those blind spots.
@pytest.mark.parametrize(
    "rel",
    [
        "pipeline/fr24_ingest.py",
        "pipeline/flight_analyzer.py",
        "pipeline/hardened_pipeline.py",
        "scripts/fr24_vision_ingest.py",
        "scripts/ocr_parallel.py",
        "scripts/rlsm_unlabeled.py",
        "pipeline/rlsm_ontology_gate.py",
        "scripts/parse_adsb_archive.py",
        "server/ingestion/registration_alerts.py",
        "server/ingestion/reconcile_registrations.py",
        "dashboard/dashboard_fr24_queue.jsx",
        "schemas/rlsm_ingest_manifest.schema.json",
        "configs/rlsm_operational_ontology.yaml",
    ],
)
def test_airspace_remnant_paths_are_flagged(tmp_path, rel):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# remnant\n", encoding="utf-8")
    state = _federation(tmp_path)
    findings = local.check_migration_remnants("spiderweb-pr", tmp_path, state)
    assert len(findings) == 1, f"{rel} should be flagged as a migration remnant"
    assert rel in findings[0].detail["paths"]


def test_legacy_parked_remnants_are_exempt(tmp_path):
    """Retired code lives under docs/legacy/ — it must not re-trigger the check."""
    for rel in (
        "docs/legacy/scripts/parse_adsb_archive.py",
        "docs/legacy/pipeline/rlsm_ontology_gate.py",
        "docs/legacy/schemas/rlsm_ingest_manifest.schema.json",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# retired\n", encoding="utf-8")
    state = _federation(tmp_path)
    assert local.check_migration_remnants("spiderweb-pr", tmp_path, state) == []


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


# ---- shared-package wiring smoke test ----


def test_run_maintenance_invokes_local_adapter(tmp_path):
    """Prove the CLI shim's local_checks injection actually reaches this repo's
    adapter through the shared prii_maintenance package."""
    (tmp_path / "fr24").mkdir()
    _federation(tmp_path)
    report = run_maintenance(
        root=tmp_path,
        mode="audit",
        write=False,
        program_id="spiderweb-pr",
        local_checks=local.run_checks,
    )
    assert any(
        f.category == "dependency_drift" and f.severity == "warning"
        for f in report.findings
    )
