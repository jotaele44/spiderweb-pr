"""
Tests for schemas/satellite_source_manifest.schema.json.

Validates directly with jsonschema.Draft7Validator — no SchemaValidator wrapper.
Skip the entire module if jsonschema is not installed.
"""

import copy
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "satellite_source_manifest.schema.json"


@pytest.fixture(scope="module")
def schema():
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def _validate(schema, doc):
    validator = jsonschema.Draft7Validator(schema)
    return list(validator.iter_errors(doc))


def _valid_manifest():
    """Minimal valid Sentinel-2-style fixture (synthetic=True)."""
    return {
        "manifest_id":    "SAT-PR-2024-001",
        "schema_version": "1.0",
        "producer":       "spiderweb-pipeline",
        "created_at":     "2024-03-14T14:32:00Z",
        "synthetic":      True,
        "source": {
            "provider":   "ESA",
            "collection": "sentinel-2-l2a",
            "platform":   "Sentinel-2A",
            "instrument": "MSI",
        },
        "acquisition": {
            "acquired_at":  "2024-03-14T14:32:00Z",
            "processed_at": "2024-03-15T02:00:00Z",
            "license":      "Copernicus Sentinel Data Terms of Use",
        },
        "asset": {
            "source_uri":      "s3://fixture-bucket/pr/sentinel2/2024-03-14.tif",
            "checksum_sha256": "a" * 64,
            "media_type":      "image/tiff",
        },
        "geometry": {
            "crs": "EPSG:4326",
            "footprint": {
                "type": "Polygon",
                "coordinates": [[
                    [-67.0, 18.0], [-66.0, 18.0],
                    [-66.0, 18.5], [-67.0, 18.5],
                    [-67.0, 18.0],
                ]],
            },
            "bbox": [-67.0, 18.0, -66.0, 18.5],
        },
        "puerto_rico": {"region": "mainland"},
        "quality": {
            "cloud_cover_pct":      12.5,
            "geometric_confidence": 0.92,
            "source_reliability":   "high",
        },
        "lineage": {"processing_pipeline": "spiderweb-sat-ingest-v1"},
    }


# ── 1. Baseline ────────────────────────────────────────────────────────────────

def test_valid_sentinel_fixture(schema):
    errors = _validate(schema, _valid_manifest())
    assert errors == [], f"Unexpected validation errors: {errors}"


# ── 2. Missing required field ──────────────────────────────────────────────────

def test_rejects_missing_required_field(schema):
    doc = _valid_manifest()
    del doc["manifest_id"]
    errors = _validate(schema, doc)
    assert len(errors) >= 1
    messages = " ".join(e.message for e in errors)
    assert "manifest_id" in messages


# ── 3. Invalid CRS ─────────────────────────────────────────────────────────────

def test_rejects_invalid_crs(schema):
    doc = _valid_manifest()
    doc["geometry"]["crs"] = "WGS84"
    errors = _validate(schema, doc)
    assert len(errors) >= 1


# ── 4. Invalid footprint type ──────────────────────────────────────────────────

def test_rejects_invalid_footprint_type(schema):
    doc = _valid_manifest()
    doc["geometry"]["footprint"]["type"] = "LineString"
    errors = _validate(schema, doc)
    assert len(errors) >= 1


# ── 5. Bbox outside Puerto Rico bounds ────────────────────────────────────────

def test_rejects_bbox_outside_pr_bounds(schema):
    doc = _valid_manifest()
    doc["geometry"]["bbox"] = [-74.3, 40.4, -73.7, 40.9]   # NYC
    errors = _validate(schema, doc)
    assert len(errors) >= 1


# ── 6. Fixture marker in asset when synthetic=false ───────────────────────────

def test_rejects_synthetic_false_with_fixture_uri(schema):
    doc = _valid_manifest()
    doc["synthetic"] = False
    # source_uri already contains "fixture" — must be rejected
    errors = _validate(schema, doc)
    assert len(errors) >= 1


def test_rejects_synthetic_false_with_mock_local_path(schema):
    doc = _valid_manifest()
    doc["synthetic"] = False
    del doc["asset"]["source_uri"]
    doc["asset"]["local_path"] = "/data/mock_pr_tile.tif"
    errors = _validate(schema, doc)
    assert len(errors) >= 1


# ── 7. Geometric confidence out of range ──────────────────────────────────────

def test_rejects_invalid_geometric_confidence(schema):
    doc = _valid_manifest()
    doc["quality"]["geometric_confidence"] = 1.5
    errors = _validate(schema, doc)
    assert len(errors) >= 1


# ── 8. Cloud cover out of range ───────────────────────────────────────────────

def test_rejects_invalid_cloud_cover_pct(schema):
    doc = _valid_manifest()
    doc["quality"]["cloud_cover_pct"] = 105.0
    errors = _validate(schema, doc)
    assert len(errors) >= 1


# ── Supplementary correctness checks ─────────────────────────────────────────

def test_synthetic_true_allows_fixture_uri(schema):
    """synthetic=True must not trigger the fixture-mode rule."""
    doc = _valid_manifest()
    assert doc["synthetic"] is True
    errors = _validate(schema, doc)
    assert errors == []


def test_asset_local_path_only_is_valid(schema):
    doc = _valid_manifest()
    del doc["asset"]["source_uri"]
    doc["asset"]["local_path"] = "/data/pr/real_tile.tif"
    errors = _validate(schema, doc)
    assert errors == []


def test_asset_missing_both_uri_and_path_rejected(schema):
    doc = _valid_manifest()
    del doc["asset"]["source_uri"]
    errors = _validate(schema, doc)
    assert len(errors) >= 1


def test_invalid_schema_version_pattern(schema):
    doc = _valid_manifest()
    doc["schema_version"] = "v1"
    errors = _validate(schema, doc)
    assert len(errors) >= 1


def test_invalid_region_enum(schema):
    doc = _valid_manifest()
    doc["puerto_rico"]["region"] = "florida"
    errors = _validate(schema, doc)
    assert len(errors) >= 1


def test_invalid_source_reliability_enum(schema):
    doc = _valid_manifest()
    doc["quality"]["source_reliability"] = "excellent"
    errors = _validate(schema, doc)
    assert len(errors) >= 1


def test_checksum_must_be_64_hex_chars(schema):
    doc = _valid_manifest()
    doc["asset"]["checksum_sha256"] = "abc123"   # too short, non-full hex
    errors = _validate(schema, doc)
    assert len(errors) >= 1


def test_schema_loadable_from_disk():
    assert _SCHEMA_PATH.exists(), f"Schema file not found: {_SCHEMA_PATH}"
    with open(_SCHEMA_PATH) as f:
        data = json.load(f)
    assert data.get("$id") == "satellite_source_manifest"
