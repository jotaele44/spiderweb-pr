"""HTTP controls for the read-only access-point API."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from server.backend import access_points_api as api  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BASE = "/v1/access-points"


def _client(repo_root: Path) -> TestClient:
    app = FastAPI()
    app.include_router(api.create_router(repo_root=repo_root))
    return TestClient(app)


@pytest.fixture()
def client():
    with _client(REPO) as c:
        yield c


@pytest.fixture()
def scratch(tmp_path):
    shutil.copytree(REPO / "registry" / "access_points", tmp_path / "registry" / "access_points")
    return tmp_path


def _floats(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _floats(value)
    elif isinstance(node, list):
        for value in node:
            yield from _floats(value)
    elif isinstance(node, float):
        yield node


def test_summary_lists_both_registries_with_provenance(client):
    body = client.get(BASE).json()
    assert [(r["registry"], r["code"], r["available"]) for r in body["registries"]] == [
        ("inland", "INAP", True), ("offshore", "OFAP", True)]
    assert all(len(r["provenance"]["sha256"]) == 64 for r in body["registries"])
    assert body["scope"]["identity_effect"] == "NONE"


def test_feature_collection_is_geojson_and_paginates_completely(client):
    response = client.get(f"{BASE}/offshore/features", params={"limit": 2})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get(f"{BASE}/offshore/features", params=params).json()
        assert page["type"] == "FeatureCollection" and page["crs"] == "OGC:CRS84"
        seen += [f["id"] for f in page["features"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 6


def test_provisional_seeds_have_no_geometry_and_no_coordinate_anywhere(client):
    page = client.get(f"{BASE}/offshore/features", params={"status": "PROVISIONAL_DISCOVERY"}).json()
    assert page["number_matched"] == 5 and page["unlocated_count"] == 5
    for feature in page["features"]:
        assert feature["geometry"] is None
        assert list(_floats(feature)) == []
        assert feature["properties"]["assertion_rung"] == "ANOMALY"
        assert not feature["properties"]["is_verified"]
    boxed = client.get(f"{BASE}/offshore/features", params={"bbox": "-68,17,-65,19"}).json()
    assert [f["id"] for f in boxed["features"]] == ["OFAP-PR-000006"] and boxed["unlocated_count"] == 5


def test_evidence_route_exposes_blockers_and_effective_tiers(client):
    body = client.get(f"{BASE}/offshore/features/OFAP-PR-000004/evidence").json()
    assert body["assertion_rung"] == "ANOMALY" and body["promotion_blockers"]
    assert body["assertions"][0]["effective_tier"] == "CANDIDATE"
    assert body["sources"][0]["provenance_state"] == "UNREGISTERED"
    one = client.get(f"{BASE}/inland/features/INAP-PR-000003")
    assert one.status_code == 200 and one.json()["geometry"]["type"] == "Point"


@pytest.mark.parametrize(
    "path, status",
    [("/inland/features/OFAP-PR-000001", 404),             # the other registry's record
     ("/offshore/features/INAP-PR-000001/evidence", 404),
     ("/inland/features/ILAP_AREA_NORTH_001", 404),        # an older naming scheme
     ("/inland/features/SW-ALL-0000012", 404),
     ("/offshore/features/OSAP-SEED-001", 404),            # a raw label is not an identity
     ("/inland/features/INAP-PR-000999", 404),
     ("/inland/features/ILAP", 400),                       # ambiguous acronym
     ("/inland/features/OSAP", 400),
     ("/inland/features/not-an-identifier", 400),
     ("/nope/features", 404),
     ("/ilap/features", 404),
     ("/inland/features?bbox=1,2", 400),
     ("/inland/features?bbox=170,10,-170,20", 400),
     ("/inland/features?status=NOPE", 400),
     ("/inland/features?feature_class=SEAFLOOR_DEPRESSION", 400),
     ("/inland/features?cursor=INAP-PR-000999", 400),
     ("/inland/features?limit=0", 422),
     ("/inland/features?limit=501", 422),
     ("/relationships?render_class=solid", 400),
     ("/relationships?feature_id=ILAP", 400),
     ("/paths?start=INAP-PR-000001", 422),
     ("/paths?start=INAP-PR-000001&goal=OFAP-PR-000006&max_hops=99", 422)],
)
def test_refusals(client, path, status):
    response = client.get(BASE + path)
    assert response.status_code == status, response.text
    body = response.json()
    assert "detail" in body and "features" not in body and "geometry" not in body


def test_relationships_paths_vocabulary_and_controls(client):
    relationships = client.get(f"{BASE}/relationships").json()
    assert relationships["number_returned"] == 0
    assert relationships["render_classes"] == ["verified", "context", "hypothesized", "contradicted",
                                               "unresolved"]
    path = client.get(f"{BASE}/paths", params={"start": "INAP-PR-000001", "goal": "OFAP-PR-000006"}).json()
    assert path["best_state"] == "NO_PATH" and path["paths"] == []
    vocabulary = client.get(f"{BASE}/vocabulary").json()
    assert [r["name"] for r in vocabulary["assertion_rungs"]] == [
        "ANOMALY", "FEATURE", "OPENING", "PASSAGE", "CONNECTION"]
    assert len(vocabulary["evidence_dimensions"]) == 8
    assert "SINKHOLE" in vocabulary["feature_classes"]["inland"]
    assert "SINKHOLE" not in vocabulary["feature_classes"]["offshore"]
    verifiable = {r["relationship_type"] for r in vocabulary["relationship_types"] if r["verifiable"]}
    assert "SPATIAL_ADJACENCY" not in verifiable and "HYPOTHESIZED_CONNECTION" not in verifiable
    section = client.get(f"{BASE}/controls/cross-section").json()
    assert section["truth_kind"] == "SYNTHETIC_CONTROL" and not section["is_continuous"]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("path", ["", "/inland/features", "/inland/features/INAP-PR-000001",
                                  "/inland/features/INAP-PR-000001/evidence", "/relationships"])
def test_api_is_read_only(client, method, path):
    assert getattr(client, method)(BASE + path).status_code == 405


def test_unlabelled_control_data_is_refused(scratch):
    app = FastAPI()
    app.include_router(api.create_router(repo_root=scratch, cross_section=lambda: {"truth_kind": "SURVEY"}))
    with TestClient(app) as c:
        assert c.get(f"{BASE}/controls/cross-section").status_code == 503


def test_tampered_or_missing_document_is_unavailable_for_that_registry_only(scratch):
    path = scratch / "registry" / "access_points" / "inland.json"
    document = json.loads(path.read_text())
    document["features"][0]["status"] = "VERIFIED"
    path.write_text(json.dumps(document))
    with _client(scratch) as c:
        assert c.get(f"{BASE}/inland/features").status_code == 503
        assert c.get(f"{BASE}/inland/sources").status_code == 503
        assert c.get(f"{BASE}/offshore/features").status_code == 200
        summary = {r["registry"]: r["available"] for r in c.get(BASE).json()["registries"]}
        assert summary == {"inland": False, "offshore": True}
    (scratch / "registry" / "access_points" / "offshore.json").unlink()
    (scratch / "registry" / "access_points" / "relationships.json").unlink()
    with _client(scratch) as c:
        assert c.get(f"{BASE}/offshore/features").status_code == 503
        assert c.get(f"{BASE}/relationships").status_code == 503
        assert c.get(BASE).status_code == 200


def test_routes_are_mounted_on_the_application_and_nothing_else_moved():
    from server.backend.main import app

    paths = app.openapi()["paths"]
    expected = {BASE, f"{BASE}/vocabulary", f"{BASE}/relationships", f"{BASE}/paths",
                f"{BASE}/controls/cross-section", f"{BASE}/{{registry}}/features",
                f"{BASE}/{{registry}}/features/{{feature_id}}",
                f"{BASE}/{{registry}}/features/{{feature_id}}/evidence", f"{BASE}/{{registry}}/sources"}
    assert expected <= set(paths)
    for path in expected:
        assert set(paths[path]) == {"get"}
    for existing in ("/health", "/sites", "/catalog", "/geo/{layer}.geojson", "/spatial/layers",
                     "/pipeline/run"):
        assert existing in paths
    with TestClient(app) as c:
        assert c.get(f"{BASE}/inland/features").json()["number_matched"] == 4


def test_desktop_catch_all_does_not_shadow_the_registry_routes():
    desktop = pytest.importorskip("desktop.app_server")
    with TestClient(desktop.app) as c:
        response = c.get(f"{BASE}/offshore/features")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/geo+json")
        assert response.json()["type"] == "FeatureCollection"
