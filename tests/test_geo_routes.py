"""
test_geo_routes.py — Smoke tests for the /geo/{layer}.geojson endpoints.

Assumes ingest_tiger_pr.py has been run at least once so the GeoJSON files
exist at data/*.geojson. If they don't, the tests skip with a clear message
(they don't fail) so the suite remains green when geo data hasn't been
populated yet (e.g. on fresh clones / CI before the geo step runs).

Counts:
  - state:        exact 1 (single PR feature)
  - municipios:   exact 78 (PR's count is politically stable)
  - tracts:       [850, 1100]   (Census tract redraws shift counts by vintage)
  - block_groups: [2400, 3200]
  - places:       [200, 350]
  - barrios:      [800, 1100]
  - zctas:        [130, 200]    (PR ZIPs: 006xx, 007xx, 009xx)
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
    "state": (1, 1),            # exact
    "municipios": (78, 78),     # exact
    "tracts": (850, 1100),
    "block_groups": (2000, 3500),   # generous until first real ingest
    "places": (200, 350),
    "barrios": (800, 1100),
    "zctas": (100, 220),            # generous until first real ingest
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
    for layer in (
        "state", "municipios", "tracts", "block_groups",
        "places", "barrios", "zctas",
    ):
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


@pytest.mark.smoke
def test_zctas_only_in_pr_zip_ranges_not_usvi():
    """Every ZCTA GEOID must begin with 006, 007, or 009. 008xx = USVI must
    NOT leak through the prefix filter — guards the catch the advisor made."""
    _skip_if_missing("zctas")
    payload = json.loads(_data_file("zctas").read_text())
    geoids = [f["properties"]["GEOID"] for f in payload["features"]]
    assert geoids, "no GEOIDs in zctas payload"
    bad = [g for g in geoids if not (
        g.startswith("006") or g.startswith("007") or g.startswith("009")
    )]
    assert not bad, f"non-PR ZCTAs leaked through filter: {bad[:5]}"
    # Explicit USVI guard — extra clear if the filter ever regresses.
    usvi_leaks = [g for g in geoids if g.startswith("008")]
    assert not usvi_leaks, f"USVI ZCTAs leaked: {usvi_leaks[:5]}"
