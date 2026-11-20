from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from spiderweb import specialized_execution as mod


@dataclass
class _Result:
    provider: str = "gibs"
    image_bytes: bytes = b"image-bytes"
    media_type: str = "image/jpeg"
    bbox: list[float] = None
    acquired_at: str | None = "2026-09-01"
    collection: str | None = "x"
    platform: str | None = "Terra"
    instrument: str | None = "MODIS"
    cloud_cover_pct: float | None = None
    resolution_m: float | None = None
    scene_id: str | None = "scene"
    source_uri: str | None = "https://example.test/source"
    cache_path: str | None = "/tmp/cache"

    def __post_init__(self):
        if self.bbox is None:
            self.bbox = [-66.2, 18.0, -66.0, 18.2]

    def to_dict(self, include_image: bool = True):
        return {
            "provider": self.provider,
            "media_type": self.media_type,
            "bbox": self.bbox,
            "acquired_at": self.acquired_at,
            "collection": self.collection,
            "platform": self.platform,
            "instrument": self.instrument,
            "cloud_cover_pct": self.cloud_cover_pct,
            "resolution_m": self.resolution_m,
            "scene_id": self.scene_id,
            "source_uri": self.source_uri,
            "cache_path": self.cache_path,
            "size_bytes": len(self.image_bytes),
        }


class _Provider:
    def fetch(self, bbox, date_range):
        assert bbox == [-66.2, 18.0, -66.0, 18.2]
        assert date_range == "2026-09-01/2026-09-02"
        return _Result()


def _plan():
    return {
        "schema_version": "spiderweb.location_query_plan.v1.1",
        "provider_registry_sha256": "a" * 64,
        "query": {"query_id": "x", "mode": "fetch"},
        "fetch_gate": "READY",
        "specialized_calls": [{
            "provider_id": "NASA_GIBS_IMAGERY",
            "execution_kind": "IMAGERY_PROVIDER_CALL",
            "identity_state": "SPECIALIZED_SOURCE_ACQUISITION",
            "provider": "gibs",
            "bbox_wgs84": [-66.2, 18.0, -66.0, 18.2],
            "date_range": "2026-09-01/2026-09-02",
        }],
    }


def test_imagery_specialized_execution_preserves_bytes(monkeypatch, tmp_path: Path) -> None:
    import imagery.providers
    monkeypatch.setattr(imagery.providers, "get_provider", lambda name: _Provider())
    result = mod.execute_specialized_calls(_plan(), tmp_path)
    assert result["state"] == "PASS"
    assert result["call_count"] == 1
    record = result["records"][0]
    assert record["bbox_equal"] is True
    assert record["bytes"] == len(b"image-bytes")
    assert Path(record["raw_path"]).read_bytes() == b"image-bytes"
    assert len(record["sha256"]) == 64
    assert record["call_spec_sha256"] == mod.canonical_json_sha256(_plan()["specialized_calls"][0])


def test_returned_bbox_drift_fails_closed(monkeypatch, tmp_path: Path) -> None:
    class _Bad(_Provider):
        def fetch(self, bbox, date_range):
            result = _Result()
            result.bbox = [-67.0, 18.0, -66.0, 18.2]
            return result

    import imagery.providers
    monkeypatch.setattr(imagery.providers, "get_provider", lambda name: _Bad())
    with pytest.raises(mod.SpecializedExecutionError, match="returned bbox drift"):
        mod.execute_specialized_calls(_plan(), tmp_path)


def test_specialized_receipt_is_immutable(monkeypatch, tmp_path: Path) -> None:
    import imagery.providers
    monkeypatch.setattr(imagery.providers, "get_provider", lambda name: _Provider())
    (tmp_path / "specialized_receipt.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(mod.SpecializedExecutionError, match="already exists"):
        mod.execute_specialized_calls(_plan(), tmp_path)
