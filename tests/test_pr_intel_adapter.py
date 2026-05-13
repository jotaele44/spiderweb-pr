"""Tests for PRIntelAdapter: 10 files created, gate status."""

import json
from pathlib import Path

import pytest

from pr_intel_adapter import PRIntelAdapter


def test_export_all_creates_required_files(populated_db, tmp_output):
    adapter = PRIntelAdapter(populated_db, str(tmp_output))
    report = adapter.export_all()

    for fname in PRIntelAdapter.REQUIRED_OUTPUTS:
        assert (tmp_output / fname).exists(), f"Missing: {fname}"


def test_integration_report_has_all_gates(populated_db, tmp_output):
    adapter = PRIntelAdapter(populated_db, str(tmp_output))
    report = adapter.export_all()

    expected_gates = {
        "schema_validation",
        "coordinate_coverage",
        "ocr_confidence_gate",
        "evidence_chain_coverage",
        "export_completeness",
        "temporal_integrity",
    }
    assert set(report["gates"].keys()) == expected_gates


def test_integration_report_overall_status_present(populated_db, tmp_output):
    adapter = PRIntelAdapter(populated_db, str(tmp_output))
    report = adapter.export_all()
    assert report["overall_status"] in ("PASS", "FAIL")


def test_integration_report_gate_status_values(populated_db, tmp_output):
    adapter = PRIntelAdapter(populated_db, str(tmp_output))
    report = adapter.export_all()
    for gate_name, gate in report["gates"].items():
        assert gate["status"] in ("PASS", "FAIL"), f"Gate {gate_name}: invalid status"


def test_source_manifest_valid_json(populated_db, tmp_output):
    PRIntelAdapter(populated_db, str(tmp_output)).export_all()
    manifest = json.loads((tmp_output / "source_manifest.json").read_text())
    assert "generated_at" in manifest
    assert "files" in manifest
    assert isinstance(manifest["files"], list)


def test_gis_features_epsg4326(populated_db, tmp_output):
    PRIntelAdapter(populated_db, str(tmp_output)).export_all()
    data = json.loads((tmp_output / "gis_airspace_features.geojson").read_text())
    crs_name = data.get("crs", {}).get("properties", {}).get("name", "")
    assert "4326" in crs_name


def test_route_lines_epsg4326(populated_db, tmp_output):
    PRIntelAdapter(populated_db, str(tmp_output)).export_all()
    data = json.loads((tmp_output / "route_lines.geojson").read_text())
    crs_name = data.get("crs", {}).get("properties", {}).get("name", "")
    assert "4326" in crs_name


def test_export_completeness_gate_passes(populated_db, tmp_output):
    adapter = PRIntelAdapter(populated_db, str(tmp_output))
    report = adapter.export_all()
    gate = report["gates"]["export_completeness"]
    assert gate["status"] == "PASS", f"Missing files: {gate.get('missing')}"


def test_integration_report_written_to_disk(populated_db, tmp_output):
    PRIntelAdapter(populated_db, str(tmp_output)).export_all()
    report_path = tmp_output / "integration_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert "overall_status" in data
    assert "gates" in data


def test_export_idempotent(populated_db, tmp_output):
    adapter = PRIntelAdapter(populated_db, str(tmp_output))
    report1 = adapter.export_all()
    report2 = adapter.export_all()
    assert report1["overall_status"] == report2["overall_status"]
