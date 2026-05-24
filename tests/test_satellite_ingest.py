"""Tests for satellite_ingest: PRII Stage 3 satellite source ingestion."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from satellite_ingest import (
    SatelliteIngestError,
    SatelliteIngestor,
    ingest_satellite,
    load_stac_catalog,
    load_synthetic_catalog,
)
from schema_validation import SchemaValidator

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SYNTHETIC_CATALOG = str(FIXTURES / "satellite_catalog.json")
STAC_CATALOG = str(FIXTURES / "satellite_stac_items.json")


# ── Synthetic ingestion ───────────────────────────────────────────────────────

def test_synthetic_ingest_validates_good_scenes(tmp_path):
    summary = ingest_satellite(str(tmp_path / "out"), SYNTHETIC_CATALOG, "synthetic")
    assert summary["catalogued"] == 4
    assert summary["validated"] == 2
    assert summary["rejected"] == 2


def test_validated_manifests_written_and_schema_clean(tmp_path):
    out = tmp_path / "out"
    ingest_satellite(str(out), SYNTHETIC_CATALOG, "synthetic")
    manifests = sorted((out / "manifests").glob("*.json"))
    assert len(manifests) == 2

    validator = SchemaValidator()
    for path in manifests:
        manifest = json.loads(path.read_text())
        result = validator.validate(manifest, "satellite_source_manifest")
        assert result["valid"], f"{path.name}: {result['errors']}"


def test_envelope_violation_rejected(tmp_path):
    summary = ingest_satellite(str(tmp_path / "out"), SYNTHETIC_CATALOG, "synthetic")
    rejected_ids = {r["scene_id"] for r in summary["rejected_scenes"]}
    assert "SAT-NYC-OUT-003" in rejected_ids


def test_fixture_mode_violation_rejected(tmp_path):
    summary = ingest_satellite(str(tmp_path / "out"), SYNTHETIC_CATALOG, "synthetic")
    rejected_ids = {r["scene_id"] for r in summary["rejected_scenes"]}
    assert "SAT-PR-S2-004" in rejected_ids


def test_rejected_scenes_written_with_errors(tmp_path):
    out = tmp_path / "out"
    ingest_satellite(str(out), SYNTHETIC_CATALOG, "synthetic")
    rejected = sorted((out / "rejected").glob("*.json"))
    assert len(rejected) == 2
    for path in rejected:
        record = json.loads(path.read_text())
        assert record["errors"], f"{path.name} should record validation errors"


def test_summary_file_written(tmp_path):
    out = tmp_path / "out"
    ingest_satellite(str(out), SYNTHETIC_CATALOG, "synthetic")
    summary = json.loads((out / "ingest_summary.json").read_text())
    for key in ("generated_at", "producer", "catalogued", "validated",
                "rejected", "manifests", "pr_envelope"):
        assert key in summary


def test_build_manifest_adds_envelope_fields(tmp_path):
    ingestor = SatelliteIngestor(str(tmp_path / "out"))
    scene = load_synthetic_catalog(SYNTHETIC_CATALOG)[0]
    manifest = ingestor.build_manifest(scene)
    assert manifest["manifest_id"] == "SAT-PR-S2-001"
    assert manifest["schema_version"] == "1.0"
    assert manifest["producer"]
    assert manifest["created_at"].endswith("Z")
    assert manifest["lineage"]["processing_pipeline"]


# ── STAC ingestion ────────────────────────────────────────────────────────────

def test_stac_catalog_parsed_and_ingested(tmp_path):
    scenes = load_stac_catalog(STAC_CATALOG)
    assert len(scenes) == 1
    assert scenes[0]["synthetic"] is False
    assert scenes[0]["source"]["platform"] == "Sentinel-2B"

    summary = ingest_satellite(str(tmp_path / "out"), STAC_CATALOG, "stac")
    assert summary["validated"] == 1
    assert summary["rejected"] == 0


def test_stac_item_with_null_numeric_props_does_not_crash():
    from satellite_ingest import _stac_item_to_scene

    item = {
        "id": "S2_NULLS",
        "collection": "sentinel-2-l2a",
        "bbox": [-67.0, 18.0, -66.0, 18.5],
        "geometry": {"type": "Polygon", "coordinates": [[[-67.0, 18.0]]]},
        "properties": {"datetime": "2024-07-01T00:00:00Z", "eo:cloud_cover": None},
        "assets": {"data": {"href": "https://example.com/x.tif", "type": "image/tiff"}},
    }
    scene = _stac_item_to_scene(item)
    assert isinstance(scene["quality"]["cloud_cover_pct"], float)
    assert isinstance(scene["quality"]["geometric_confidence"], float)


# ── Error handling ────────────────────────────────────────────────────────────

def test_missing_catalog_raises(tmp_path):
    with pytest.raises(SatelliteIngestError):
        load_synthetic_catalog(str(tmp_path / "does_not_exist.json"))


def test_malformed_catalog_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SatelliteIngestError):
        load_synthetic_catalog(str(bad))


# ── CLI wiring ────────────────────────────────────────────────────────────────

def _run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "run_all.py"] + args,
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def test_ingest_satellite_cli(tmp_path):
    out = tmp_path / "cli_out"
    result = _run(["--db", str(tmp_path / "smoke.db"),
                   "--ingest-satellite", str(out),
                   "--sat-source", "synthetic",
                   "--sat-catalog", SYNTHETIC_CATALOG])
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((out / "ingest_summary.json").read_text())
    assert summary["validated"] == 2


def test_ingest_satellite_cli_missing_catalog_exits_nonzero(tmp_path):
    result = _run(["--db", str(tmp_path / "smoke.db"),
                   "--ingest-satellite", str(tmp_path / "out"),
                   "--sat-catalog", str(tmp_path / "nope.json")])
    assert result.returncode != 0
