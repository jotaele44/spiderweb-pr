"""/gis/* endpoints against the committed natural-features gazetteer (1,982 points).

The gazetteer is the one GIS layer whose artifact is checked in
(registry/natural_features/pr_natural_features.geojson), so these tests run on
fresh clones without the TIGER ingest.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
GAZ = "gazetteer_pr_domestic_names"
GAZ_PATH = REPO_ROOT / "registry" / "natural_features" / "pr_natural_features.geojson"
PR_BBOX = {"type": "bbox", "west": -67.95, "south": 17.85, "east": -65.2, "north": 18.6}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from server.backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def gazetteer():
    return json.loads(GAZ_PATH.read_text(encoding="utf-8"))["features"]


def _schema(name: str) -> dict:
    return json.loads((REPO_ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_catalog_endpoint_validates_and_reports_data_availability(client):
    resp = client.get("/gis/catalog")
    assert resp.status_code == 200
    document = resp.json()
    jsonschema.validate(document, _schema("gis_layer_catalog_v1.schema.json"))
    by_id = {layer["layer_id"]: layer for layer in document["layers"]}
    assert by_id[GAZ]["data_available"] is True
    assert by_id[GAZ]["search_fields"]


def test_query_counts_match_an_independent_bbox_count(client, gazetteer):
    west, south, east, north = -66.2, 18.2, -65.9, 18.45
    expected = sum(
        1
        for f in gazetteer
        if west <= f["geometry"]["coordinates"][0] <= east
        and south <= f["geometry"]["coordinates"][1] <= north
    )
    body = {
        "geometry": {
            "type": "bbox",
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        },
        "layers": [GAZ],
    }
    resp = client.post("/gis/query", json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    jsonschema.validate(payload, _schema("gis_query_v1.schema.json"))
    assert payload["total_matched"] == expected > 0
    assert payload["evidence_state"] == "COMPUTED"
    assert sum(payload["summary"]["classes"][GAZ]["feature_class"].values()) == min(
        expected, 500
    )


def test_query_rejects_unknown_layers_and_bad_geometry(client):
    assert (
        client.post(
            "/gis/query", json={"geometry": PR_BBOX, "layers": ["nope"]}
        ).status_code
        == 400
    )
    bad = {
        "geometry": {
            "type": "bbox",
            "west": -65,
            "south": 18,
            "east": -66,
            "north": 18.5,
        },
        "layers": [GAZ],
    }
    assert client.post("/gis/query", json=bad).status_code == 422


def test_identify_finds_a_known_feature_at_its_coordinates(client, gazetteer):
    target = gazetteer[0]
    lon, lat = target["geometry"]["coordinates"]
    resp = client.get(
        "/gis/identify", params={"lon": lon, "lat": lat, "layers": GAZ, "tol_m": 5}
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["hits"][0]["feature_id"] == target["properties"]["canonical_id"]
    assert payload["hits"][0]["distance_m"] == 0
    assert set(payload["hits"][0]["properties"]) <= {
        "canonical_name",
        "feature_class",
        "feature_type",
        "municipality",
        "gnis_id",
        "canonical_id",
    }
    grid = payload["location"]["grid_v2"]
    assert grid["binding"] == "CURSOR_LOOKUP_NOT_RECORD_BINDING"
    assert grid["status"] in {"OK", "OUTSIDE", "UNAVAILABLE"}


def test_search_by_name_and_by_coordinate(client, gazetteer):
    name = gazetteer[0]["properties"]["canonical_name"]
    resp = client.get("/gis/search", params={"q": name, "layers": GAZ})
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert hits and hits[0]["rank"] == 0 and hits[0]["label"] == name
    coord = client.get("/gis/search", params={"q": "18.4723, -66.7156"}).json()["hits"][
        0
    ]
    assert coord["kind"] == "coordinate" and coord["anchor"] == [-66.7156, 18.4723]


def test_export_csv_for_public_layer(client):
    body = {
        "geometry": {"type": "radius", "lon": -66.1, "lat": 18.3, "radius_m": 8000},
        "layers": [GAZ],
        "format": "csv",
    }
    resp = client.post("/gis/export", json=body)
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert all(row["layer_id"] == GAZ for row in rows)


def test_export_refuses_non_public_layers(client):
    body = {"geometry": PR_BBOX, "layers": ["anomalies"], "format": "geojson"}
    assert client.post("/gis/export", json=body).status_code == 403
