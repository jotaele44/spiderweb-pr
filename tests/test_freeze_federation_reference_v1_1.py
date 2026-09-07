import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_federation_reference_v1_1.py"
spec = importlib.util.spec_from_file_location("freeze_federation_reference", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.status = 200
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def feature(stable_id):
    return {
        "type": "Feature",
        "properties": {"GEOID": stable_id},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-66.0, 18.0], [-66.1, 18.0], [-66.0, 18.0]]],
        },
    }


def source_spec():
    return {
        "endpoint": "https://example.invalid/MapServer/0/query",
        "where": "STATE='72'",
        "expected_min": 3,
        "stable_id": "GEOID",
        "authority": "Test Authority",
        "declared_vintage": "2026-01-01",
    }


def paginated_urlopen(request, timeout):
    assert timeout == 120
    parsed = urlparse(request.full_url)
    query = parse_qs(parsed.query)
    if not parsed.path.endswith("/query"):
        return FakeResponse(
            {
                "name": "Test layer",
                "type": "Feature Layer",
                "currentVersion": 11.5,
                "maxRecordCount": 2,
                "advancedQueryCapabilities": {"supportsPagination": True},
                "fields": [{"name": "GEOID", "type": "esriFieldTypeString"}],
            }
        )
    if query.get("returnCountOnly") == ["true"]:
        return FakeResponse({"count": 3})
    offset = int(query["resultOffset"][0])
    pages = {
        0: [feature("001"), feature("002")],
        2: [feature("003")],
    }
    return FakeResponse(
        {
            "type": "FeatureCollection",
            "features": pages[offset],
            "exceededTransferLimit": offset == 0,
        }
    )


def test_freeze_preserves_count_and_all_raw_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "urlopen", paginated_urlopen)
    result = module.freeze_one("municipios", source_spec(), tmp_path, page_size=2)

    assert result["feature_count"] == 3
    assert result["stable_id_unique_count"] == 3
    assert [page["offset"] for page in result["raw_pages"]] == [0, 2]
    assert result["count_receipt"]["count"] == 3
    assert result["service_metadata_receipt"]["stable_id_field_type"] == (
        "esriFieldTypeString"
    )
    assert result["declared_vintage_evidence_state"] == "ASSUMPTION"
    assert result["artifact_identity"] == "LOGICAL_COMPOSITE"
    assert len(result["payload_multiset"]) == 2
    assert all(len(page["sha256"]) == 64 for page in result["raw_pages"])
    logical = json.loads((tmp_path / result["artifact"]).read_text(encoding="utf-8"))
    assert [row["properties"]["GEOID"] for row in logical["features"]] == [
        "001",
        "002",
        "003",
    ]


def test_duplicate_ids_across_pages_fail_closed(monkeypatch, tmp_path):
    def duplicate_urlopen(request, timeout):
        response = paginated_urlopen(request, timeout)
        query = parse_qs(urlparse(request.full_url).query)
        if query.get("resultOffset") == ["2"]:
            return FakeResponse(
                {"type": "FeatureCollection", "features": [feature("002")]}
            )
        return response

    monkeypatch.setattr(module, "urlopen", duplicate_urlopen)
    with pytest.raises(RuntimeError, match="duplicate GEOID"):
        module.freeze_one("municipios", source_spec(), tmp_path, page_size=2)


def test_empty_page_before_count_closure_fails_closed(monkeypatch, tmp_path):
    def incomplete_urlopen(request, timeout):
        parsed = urlparse(request.full_url)
        if not parsed.path.endswith("/query"):
            return paginated_urlopen(request, timeout)
        query = parse_qs(parsed.query)
        if query.get("returnCountOnly") == ["true"]:
            return FakeResponse({"count": 3})
        return FakeResponse({"type": "FeatureCollection", "features": []})

    monkeypatch.setattr(module, "urlopen", incomplete_urlopen)
    with pytest.raises(RuntimeError, match="pagination incomplete"):
        module.freeze_one("municipios", source_spec(), tmp_path, page_size=2)


def test_stable_id_field_type_must_preserve_leading_zeroes(monkeypatch, tmp_path):
    def numeric_id_metadata(request, timeout):
        parsed = urlparse(request.full_url)
        if not parsed.path.endswith("/query"):
            return FakeResponse(
                {
                    "name": "Test layer",
                    "type": "Feature Layer",
                    "maxRecordCount": 2,
                    "fields": [{"name": "GEOID", "type": "esriFieldTypeInteger"}],
                }
            )
        return paginated_urlopen(request, timeout)

    monkeypatch.setattr(module, "urlopen", numeric_id_metadata)
    with pytest.raises(RuntimeError, match="must be esriFieldTypeString"):
        module.freeze_one("municipios", source_spec(), tmp_path, page_size=2)
