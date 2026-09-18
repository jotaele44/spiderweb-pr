from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "location_query_fetch.py"
spec = importlib.util.spec_from_file_location("location_query_fetch", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_executor_rejects_plan_mode_before_network(tmp_path: Path) -> None:
    plan = {
        "query": {"mode": "plan"},
        "requests": [{
            "method": "GET",
            "provider_id": "X",
            "request_role": "should_not_execute",
            "url": "https://example.invalid/",
        }],
    }
    with pytest.raises(SystemExit, match="requires query.mode=fetch"):
        mod.execute(plan, tmp_path)


def test_executor_accepts_empty_fetch_plan_without_network(tmp_path: Path) -> None:
    plan = {"query": {"mode": "fetch"}, "fetch_gate": "READY", "requests": []}
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PASS"
    assert result["query_mode"] == "fetch"
    assert result["request_count"] == 0
    assert result["raw_bytes_preserved_before_derivation"] is True


def test_safe_name_is_deterministic() -> None:
    assert mod.safe_name("USFWS_NWI", "wetlands", 1) == "001_USFWS_NWI_wetlands"


def test_post_request_requires_explicit_json_body_and_serializes_deterministically() -> None:
    spec = {
        "method": "POST",
        "url": "https://example.invalid/post",
        "json_body": {"query": "SELECT 1", "format": "JSON+COLUMNNAME"},
    }
    request, method = mod._request_from_spec(spec, 1)
    assert method == "POST"
    assert request.full_url == spec["url"]
    assert json.loads(request.data.decode("utf-8")) == spec["json_body"]
    assert request.get_header("Content-type") == "application/json"


def test_post_request_without_body_fails_closed() -> None:
    with pytest.raises(SystemExit, match="requires json_body object"):
        mod._request_from_spec({"method": "POST", "url": "https://example.invalid/post"}, 1)


def test_unknown_method_fails_closed() -> None:
    with pytest.raises(SystemExit, match="unsupported method"):
        mod._request_from_spec({"method": "DELETE", "url": "https://example.invalid/"}, 1)


class _FakeHeaders(dict):
    def get(self, key: str, default: str = "") -> str:
        return super().get(key, default)


class _FakeResponse:
    def __init__(self, payload: object, *, status: int = 200, content_type: str = "application/json") -> None:
        self.status = status
        self.headers = _FakeHeaders({"Content-Type": content_type})
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _arcgis_spec() -> dict:
    return {
        "protocol": "ARCGIS_FEATURE_LAYER",
        "method": "GET",
        "provider_id": "USFWS_NWI",
        "request_role": "wetlands",
        "identity_state": "SOURCE_MANIFESTATION",
        "url": "https://example.invalid/FeatureServer/0/query?returnIdsOnly=true&f=json",
        "layer_url": "https://example.invalid/FeatureServer/0",
        "out_fields": "*",
    }


def test_arcgis_executor_closes_object_id_denominator(monkeypatch, tmp_path: Path) -> None:
    responses = iter([
        _FakeResponse({"objectIdFieldName": "OBJECTID", "objectIds": [3, 1, 2]}),
        _FakeResponse({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"OBJECTID": 1}, "geometry": None},
                {"type": "Feature", "properties": {"OBJECTID": 2}, "geometry": None},
                {"type": "Feature", "properties": {"OBJECTID": 3}, "geometry": None},
            ],
        }, content_type="application/geo+json"),
    ])
    monkeypatch.setattr(mod, "urlopen", lambda request, timeout=0: next(responses))
    plan = {"query": {"mode": "fetch"}, "fetch_gate": "READY", "requests": [_arcgis_spec()]}
    result = mod.execute(plan, tmp_path)
    receipt = result["requests"][0]
    assert result["state"] == "PASS"
    assert receipt["state"] == "PASS"
    assert receipt["denominator_id_count"] == 3
    assert receipt["returned_id_count"] == 3
    assert receipt["batch_count"] == 1
    assert receipt["id_set_equal"] is True
    assert receipt["arithmetic_closure"] is True
    assert Path(receipt["id_denominator_raw_path"]).is_file()
    assert len(receipt["batches"]) == 1


def test_arcgis_zero_ids_is_explicit_no_coverage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "urlopen",
        lambda request, timeout=0: _FakeResponse(
            {"objectIdFieldName": "OBJECTID", "objectIds": []}
        ),
    )
    result = mod.execute(
        {"query": {"mode": "fetch"}, "fetch_gate": "READY", "requests": [_arcgis_spec()]},
        tmp_path,
    )
    receipt = result["requests"][0]
    assert result["state"] == "PASS"
    assert result["no_coverage_count"] == 1
    assert receipt["state"] == "NO_COVERAGE"
    assert receipt["denominator_id_count"] == 0
    assert receipt["arithmetic_closure"] is True


def test_arcgis_missing_returned_id_fails_closed(monkeypatch, tmp_path: Path) -> None:
    responses = iter([
        _FakeResponse({"objectIdFieldName": "OBJECTID", "objectIds": [1, 2, 3]}),
        _FakeResponse({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"OBJECTID": 1}, "geometry": None},
                {"type": "Feature", "properties": {"OBJECTID": 2}, "geometry": None},
            ],
        }, content_type="application/geo+json"),
    ])
    monkeypatch.setattr(mod, "urlopen", lambda request, timeout=0: next(responses))
    with pytest.raises(SystemExit, match="ID mismatch"):
        mod.execute(
            {"query": {"mode": "fetch"}, "requests": [_arcgis_spec()]},
            tmp_path,
        )


def test_arcgis_duplicate_denominator_ids_fail_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "urlopen",
        lambda request, timeout=0: _FakeResponse(
            {"objectIdFieldName": "OBJECTID", "objectIds": [1, 1]}
        ),
    )
    with pytest.raises(SystemExit, match="duplicate IDs in denominator"):
        mod.execute(
            {"query": {"mode": "fetch"}, "requests": [_arcgis_spec()]},
            tmp_path,
        )


def test_executor_rejects_blocked_fetch_gate_before_network(tmp_path: Path) -> None:
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "BLOCKED_INCOMPLETE_PROVIDER_EXECUTION",
        "fetch_blocker_provider_ids": ["NASA_GIBS_IMAGERY"],
        "requests": [],
    }
    with pytest.raises(SystemExit, match="fetch_gate=BLOCKED_INCOMPLETE_PROVIDER_EXECUTION"):
        mod.execute(plan, tmp_path)


def test_executor_allows_explicit_partial_gate_without_requests(tmp_path: Path) -> None:
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS",
        "fetch_blocker_provider_ids": ["NASA_GIBS_IMAGERY"],
        "requests": [],
    }
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PARTIAL"
    assert result["fetch_gate"] == "ALLOW_PARTIAL_WITH_EXPLICIT_GAPS"
    assert result["fetch_blocker_provider_ids"] == ["NASA_GIBS_IMAGERY"]


def test_executor_refuses_to_overwrite_existing_snapshot(tmp_path: Path) -> None:
    (tmp_path / "fetch_receipt.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="output snapshot already exists"):
        mod.execute(
            {"query": {"mode": "fetch"}, "fetch_gate": "READY", "requests": []},
            tmp_path,
        )


def test_simple_ogc_empty_features_is_no_coverage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "urlopen",
        lambda request, timeout=0: _FakeResponse(
            {"type": "FeatureCollection", "features": [], "numberMatched": 0, "numberReturned": 0},
            content_type="application/geo+json",
        ),
    )
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "READY",
        "requests": [{
            "protocol": "OGC_FEATURES",
            "method": "GET",
            "provider_id": "X",
            "request_role": "features",
            "identity_state": "SOURCE_MANIFESTATION",
            "url": "https://example.invalid/items?f=json",
            "media_type": "application/geo+json",
        }],
    }
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PASS"
    assert result["no_coverage_count"] == 1
    assert result["requests"][0]["state"] == "NO_COVERAGE"


def test_simple_ogc_next_link_fails_closed_as_incomplete(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "urlopen",
        lambda request, timeout=0: _FakeResponse({
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": None}],
            "numberMatched": 2,
            "numberReturned": 1,
            "links": [{"rel": "next", "href": "https://example.invalid/page2"}],
        }, content_type="application/geo+json"),
    )
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "READY",
        "requests": [{
            "protocol": "OGC_FEATURES",
            "method": "GET",
            "provider_id": "X",
            "request_role": "features",
            "identity_state": "SOURCE_MANIFESTATION",
            "url": "https://example.invalid/items?f=json",
            "media_type": "application/geo+json",
        }],
    }
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PARTIAL_OR_BLOCKED"
    assert result["failure_count"] == 1
    assert result["requests"][0]["state"] == "INCOMPLETE_PAGINATION_REQUIRED"


def test_simple_arcgis_metadata_json_error_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mod,
        "urlopen",
        lambda request, timeout=0: _FakeResponse({"error": {"code": 400, "message": "bad"}}),
    )
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "READY",
        "requests": [{
            "protocol": "ARCGIS_METADATA",
            "method": "GET",
            "provider_id": "X",
            "request_role": "metadata",
            "identity_state": "DISCOVERY",
            "url": "https://example.invalid/?f=json",
            "media_type": "application/json",
        }],
    }
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PARTIAL_OR_BLOCKED"
    assert result["requests"][0]["state"] == "FAIL_PROVIDER_ERROR"


def test_simple_wfs_exception_document_fails(monkeypatch, tmp_path: Path) -> None:
    class _XmlResponse:
        status = 200
        headers = _FakeHeaders({"Content-Type": "text/xml"})
        def read(self) -> bytes:
            return b"<ServiceExceptionReport><ServiceException>bad</ServiceException></ServiceExceptionReport>"
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(mod, "urlopen", lambda request, timeout=0: _XmlResponse())
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "READY",
        "requests": [{
            "protocol": "WFS_FEATURES",
            "method": "GET",
            "provider_id": "SSURGO_SOILS",
            "request_role": "MapunitPoly",
            "identity_state": "SOURCE_MANIFESTATION",
            "url": "https://example.invalid/wfs",
            "media_type": "application/gml+xml",
        }],
    }
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PARTIAL_OR_BLOCKED"
    assert result["requests"][0]["state"] == "FAIL_PROVIDER_ERROR"


def test_simple_sda_requires_table_list(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "urlopen", lambda request, timeout=0: _FakeResponse({"not_table": []}))
    plan = {
        "query": {"mode": "fetch"},
        "fetch_gate": "READY",
        "requests": [{
            "protocol": "SDA_TABULAR",
            "method": "POST",
            "provider_id": "SSURGO_SOILS",
            "request_role": "mapunit",
            "identity_state": "DEPENDENT_PRODUCTION_ACQUISITION",
            "url": "https://example.invalid/post",
            "json_body": {"query": "SELECT 1", "format": "JSON+COLUMNNAME"},
            "media_type": "application/json",
        }],
    }
    result = mod.execute(plan, tmp_path)
    assert result["state"] == "PARTIAL_OR_BLOCKED"
    assert result["requests"][0]["state"] == "FAIL_SEMANTIC"
