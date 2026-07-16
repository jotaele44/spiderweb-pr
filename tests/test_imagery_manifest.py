"""
Tests for imagery.manifest — the bridge into the satellite-ingest pipeline.

Asserts a manifest built from a fetch result validates against the existing
satellite_source_manifest schema and is accepted by SatelliteIngest (dry-run).
"""

import io

import pytest

# Skip cleanly when the optional `imagery` extra is not installed.
pytest.importorskip("PIL")

from imagery.manifest import build_manifest
from imagery.models import ImageryResult
from readiness.satellite_ingest import SatelliteIngest


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (12, 34, 56)).save(buf, format="PNG")
    return buf.getvalue()


def _result(cloud=3.1, cache_path=None) -> ImageryResult:
    return ImageryResult(
        provider="sentinelhub",
        image_bytes=_png_bytes(),
        media_type="image/png",
        bbox=[-66.45, 18.15, -66.35, 18.25],
        acquired_at="2024-01-20T15:00:00Z",
        collection="sentinel-2-l2a",
        platform="Sentinel-2",
        instrument="MSI",
        cloud_cover_pct=cloud,
        resolution_m=10.0,
        scene_id="S2B_TEST",
        cache_path=cache_path,
    )


def test_manifest_has_required_shape():
    doc = build_manifest(_result(), synthetic=True)
    for key in (
        "manifest_id", "schema_version", "producer", "created_at", "synthetic",
        "source", "acquisition", "asset", "geometry", "puerto_rico", "quality", "lineage",
    ):
        assert key in doc
    assert len(doc["asset"]["checksum_sha256"]) == 64
    assert doc["geometry"]["crs"] == "EPSG:4326"
    assert doc["quality"]["cloud_cover_pct"] == 3.1
    assert doc["quality"]["resolution_m"] == 10.0


def test_manifest_cloud_none_is_unverified():
    doc = build_manifest(_result(cloud=None), synthetic=True)
    assert doc["quality"]["cloud_cover_pct"] == 0.0
    assert doc["quality"]["source_reliability"] == "unverified"


def test_manifest_accepted_by_satellite_ingest(tmp_path):
    import json

    doc = build_manifest(_result(), synthetic=True)
    path = tmp_path / "imagery_manifest.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = SatelliteIngest(dry_run=True).ingest(str(path))
    assert result["status"] == "accepted", result["errors"]
    assert result["errors"] == []


def test_manifest_bbox_clamped_into_pr_envelope():
    # A footprint spilling past the island must clamp so ingest still accepts it.
    r = _result()
    r.bbox = [-70.0, 10.0, -60.0, 30.0]
    doc = build_manifest(r, synthetic=True)
    west, south, east, north = doc["geometry"]["bbox"]
    assert -68.2 <= west <= -65.1
    assert 17.8 <= south <= 18.7
    assert -68.2 <= east <= -65.1
    assert 17.8 <= north <= 18.7
