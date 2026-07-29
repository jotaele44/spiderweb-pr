"""
test_geo_routes.py — Smoke tests for the /geo/{layer}.geojson endpoints.

Assumes ingest_tiger_pr.py has been run at least once so the GeoJSON files
exist at data/*.geojson. If they don't, the tests skip with a clear message
(they don't fail) so the suite remains green when geo data hasn't been
populated yet (e.g. on fresh clones / CI before the geo step runs).

Counts:
  - municipios: exact 78 (PR's count is politically stable)
  - tracts:     [850, 1100]   (Census tract redraws shift counts by vintage)
  - places:     [200, 350]
  - barrios:    [800, 1100]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Make the server package importable so we can instantiate the FastAPI app.
sys.path.insert(0, str(REPO_ROOT))


def _data_file(layer: str) -> Path:
    return DATA_DIR / f"{layer}.geojson"


def _skip_if_missing(layer: str) -> None:
    path = _data_file(layer)
    if not path.exists():
        pytest.skip(
            f"data/{layer}.geojson missing — run "
            f"`python server/ingestion/ingest_tiger_pr.py` to populate."
        )


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient with lifespan (runs startup migrations)."""
    from fastapi.testclient import TestClient

    from server.backend.main import app

    with TestClient(app) as c:
        yield c


COUNT_EXPECTATIONS = {
    "municipios": (78, 78),     # exact
    "tracts": (850, 1100),
    "places": (200, 350),
    "barrios": (800, 1100),
}


@pytest.mark.smoke
@pytest.mark.parametrize("layer", list(COUNT_EXPECTATIONS.keys()))
def test_layer_serves_200_with_plausible_feature_count(client, layer):
    _skip_if_missing(layer)
    resp = client.get(f"/geo/{layer}.geojson")
    assert resp.status_code == 200, f"{layer}: status {resp.status_code}"

    payload = resp.json()
    assert payload["type"] == "FeatureCollection"
    n = len(payload["features"])

    lo, hi = COUNT_EXPECTATIONS[layer]
    assert lo <= n <= hi, f"{layer}: {n} features not in [{lo}, {hi}]"


def test_unknown_layer_rejected(client):
    resp = client.get("/geo/not_a_real_layer.geojson")
    assert resp.status_code == 400


def test_catalogued_missing_geometry_is_explicit(client, monkeypatch):
    """Catalog membership never implies a fabricated empty geometry payload."""
    from server.backend import main

    monkeypatch.setattr(main, "_find_geojson", lambda _layer: None)
    layer = next(
        layer_id
        for layer_id in sorted(main._ALLOWED_LAYERS)
        if layer_id not in {"sites", "anomalies"}
    )
    resp = client.get(f"/geo/{layer}.geojson")
    assert resp.status_code == 404
    assert "has not been materialized" in resp.json()["detail"]


def test_database_geometry_missing_is_explicit(client, monkeypatch, tmp_path):
    from server.backend import main

    monkeypatch.setattr(main, "DB_PATH", tmp_path / "missing.db")
    monkeypatch.setattr(main, "_find_geojson", lambda _layer: None)
    resp = client.get("/geo/sites.geojson")
    assert resp.status_code == 503
    assert "database missing" in resp.json()["detail"]


def test_catalog_reports_runtime_status_and_provenance(client):
    resp = client.get("/catalog")
    assert resp.status_code == 200
    layers = [
        layer
        for family in resp.json()["families"]
        for layer in family["layers"]
    ]
    assert layers
    for layer in layers:
        assert layer["runtime_status"] in {
            "live",
            "empty",
            "unavailable",
            "deferred",
        }
        assert layer["endpoint"] == f"/geo/{layer['layer_id']}.geojson"
        assert layer["provenance"]["catalog"] == "configs/layer_catalog.yaml"
        assert layer["provenance"]["geometry_source"] in {
            "exported_geojson",
            "sqlite",
            "not_materialized",
        }


@pytest.mark.smoke
def test_content_type_is_json_or_geojson(client):
    """The route declares media_type='application/geo+json' but middleware
    sometimes normalises this to application/json — accept either."""
    _skip_if_missing("municipios")
    resp = client.get("/geo/municipios.geojson")
    ct = resp.headers.get("content-type", "")
    assert ct.startswith("application/json") or ct.startswith(
        "application/geo+json"
    ), f"unexpected content-type: {ct}"


@pytest.mark.smoke
def test_feature_coords_within_pr_bbox(client):
    """Sample one feature per polygon layer and assert its first coordinate
    falls inside PR's bbox (-68..-65, 17..19) in WGS84."""
    for layer in ("municipios", "tracts", "places", "barrios"):
        _skip_if_missing(layer)
        resp = client.get(f"/geo/{layer}.geojson")
        feat = resp.json()["features"][0]
        coords = feat["geometry"]["coordinates"]
        # Walk into nested arrays until we hit a [lon, lat] pair.
        while isinstance(coords, list) and coords and isinstance(coords[0], list):
            coords = coords[0]
        assert isinstance(coords, list) and len(coords) >= 2, (
            f"{layer}: could not locate coordinate pair"
        )
        lon, lat = coords[0], coords[1]
        assert -68.0 <= lon <= -65.0, f"{layer}: lon {lon} out of PR bbox"
        assert 17.0 <= lat <= 19.0, f"{layer}: lat {lat} out of PR bbox"


@pytest.mark.smoke
def test_municipios_geoids_start_with_state_fips_72(client):
    """Every municipio GEOID must begin with PR's STATEFP=72."""
    _skip_if_missing("municipios")
    resp = client.get("/geo/municipios.geojson")
    geoids = [f["properties"]["GEOID"] for f in resp.json()["features"]]
    assert geoids, "no GEOIDs in municipios payload"
    bad = [g for g in geoids if not g.startswith("72")]
    assert not bad, f"non-PR GEOIDs leaked through filter: {bad[:5]}"
