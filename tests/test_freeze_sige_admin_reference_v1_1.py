import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_sige_admin_reference_v1_1.py"
spec = importlib.util.spec_from_file_location("freeze_sige_admin", SCRIPT)
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


def source_spec(candidate_fields=("Nombre",), expected_min=2):
    return {
        "endpoint": "https://example.invalid/MapServer/2/query",
        "expected_min": expected_min,
        "candidate_fields": list(candidate_fields),
    }


def fake_urlopen(request, timeout):
    assert timeout == 120
    parsed = urlparse(request.full_url)
    query = parse_qs(parsed.query)
    if not parsed.path.endswith("/query"):
        return FakeResponse(
            {
                "id": 2,
                "name": "Límite de Municipio",
                "description": "test",
                "geometryType": "esriGeometryPolygon",
                "sourceSpatialReference": {"wkid": 32161, "latestWkid": 32161},
                "maxRecordCount": 1000,
                "fields": [
                    {"name": "OBJECTID"},
                    {"name": "Nombre"},
                    {"name": "MUNICIPIO"},
                    {"name": "BARRIO"},
                ],
            }
        )
    if query.get("returnCountOnly") == ["true"]:
        return FakeResponse({"count": 2})
    if query.get("f") == ["json"]:
        return FakeResponse(
            {
                "features": [
                    {"attributes": {"OBJECTID": 1, "Nombre": "Adjuntas"}, "geometry": {"rings": []}},
                    {"attributes": {"OBJECTID": 2, "Nombre": "Aguada"}, "geometry": {"rings": []}},
                ]
            }
        )
    return FakeResponse(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"OBJECTID": 1, "Nombre": "Adjuntas"}, "geometry": {"type": "Polygon", "coordinates": [[[-66, 18], [-66.1, 18], [-66, 18]]]}},
                {"type": "Feature", "properties": {"OBJECTID": 2, "Nombre": "Aguada"}, "geometry": {"type": "Polygon", "coordinates": [[[-67, 18], [-67.1, 18], [-67, 18]]]}},
            ],
        }
    )


def test_freeze_preserves_native_and_transformed_manifests(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    result = module.freeze_one("municipios", source_spec(), tmp_path)
    assert result["feature_count"] == 2
    assert result["source_native_crs"] == "EPSG:32161"
    assert result["canonical_comparison_crs"] == "EPSG:4326"
    assert result["stable_identifier"] is None
    assert result["identity_state"] == "CANDIDATE_NOT_IDENTITY"
    assert result["candidate_unique_count"] == 2
    assert result["duplicate_candidate_keys"] == []
    assert len(result["source_native_pages"]) == 1
    assert len(result["canonical_pages"]) == 1
    assert len(result["source_native_pages"][0]["sha256"]) == 64
    assert len(result["canonical_pages"][0]["sha256"]) == 64


def test_duplicate_candidate_names_are_retained_as_ambiguity(monkeypatch, tmp_path):
    def duplicate_urlopen(request, timeout):
        response = fake_urlopen(request, timeout)
        query = parse_qs(urlparse(request.full_url).query)
        if query.get("f") == ["geojson"]:
            payload = json.loads(response.payload)
            payload["features"][1]["properties"]["Nombre"] = "Adjuntas"
            return FakeResponse(payload)
        return response

    monkeypatch.setattr(module, "urlopen", duplicate_urlopen)
    result = module.freeze_one("municipios", source_spec(), tmp_path)
    assert result["candidate_unique_count"] == 1
    assert result["duplicate_candidate_keys"] == ["adjuntas"]
    assert result["identity_state"] == "CANDIDATE_NOT_IDENTITY"


def test_source_crs_must_be_epsg_32161(monkeypatch, tmp_path):
    def wrong_crs(request, timeout):
        parsed = urlparse(request.full_url)
        if not parsed.path.endswith("/query"):
            return FakeResponse(
                {
                    "id": 2,
                    "name": "bad",
                    "geometryType": "esriGeometryPolygon",
                    "sourceSpatialReference": {"wkid": 4326},
                    "maxRecordCount": 1000,
                    "fields": [{"name": "Nombre"}],
                }
            )
        return fake_urlopen(request, timeout)

    monkeypatch.setattr(module, "urlopen", wrong_crs)
    with pytest.raises(RuntimeError, match="expected source EPSG:32161"):
        module.freeze_one("municipios", source_spec(), tmp_path)


def test_candidate_fields_must_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="missing candidate fields"):
        module.freeze_one(
            "barrios", source_spec(candidate_fields=("MUNICIPIO", "NOPE")), tmp_path
        )
