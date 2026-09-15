"""Bounded synthetic regressions, not a live-source or acquisition certificate."""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The repository base test job does not install the optional geo extra.
# The dedicated AOI workflow installs it and runs this entire denominator.
pytest.importorskip("pyproj", reason="AOI planner tests require the geo extra")

from server.backend import aoi_api
from server.backend.aoi_planner import build_plan, digest, strict_json, valid_polygon


def square(x, y, w=1):
    return {"type": "Polygon", "coordinates": [[[x,y],[x+w,y],[x+w,y+w],[x,y+w],[x,y]]]}


def feature(geometry, asset_id="tile/a.tif", **properties):
    return {"type": "Feature", "geometry": geometry, "properties": {
        "asset_id": asset_id, "source_url": "https://example.invalid/" + asset_id,
        "product": "bare_earth_dem", "size_bytes": 100, **properties,
    }}


def configured(tmp_path, features):
    raw = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    (tmp_path / "tiles.geojson").write_bytes(raw)
    return {"providers": {"fixture": {"provider_id": "TEST_ONLY", "catalog_type": "geojson",
        "catalog_path": "tiles.geojson", "catalog_record_count": len(features),
        "catalog_sha256": hashlib.sha256(raw).hexdigest()}}}


def plan(tmp_path, features, **request):
    return build_plan({"aoi": square(0, 0, 3), **request}, configured(tmp_path, features), tmp_path)


def test_basic_freeze_and_no_fetch(tmp_path):
    result = plan(tmp_path, [feature(square(1, 1))])
    assert result["planning_gate"] == "PASS"
    assert result["state"] == "PLAN_READY"
    assert not result["capabilities"]["fetch"]
    assert result["coverage"] is None and result["coverage_state"] == "UNKNOWN"
    assert result["certification"] == "OPEN"
    sha = result.pop("plan_sha256")
    assert result.pop("plan_id") == f"aoi-{sha}"
    assert digest(result) == sha


def test_hole_not_bbox_inclusion(tmp_path):
    aoi = square(0, 0, 4)
    aoi["coordinates"].append(square(1, 1, 2)["coordinates"][0])
    result = plan(tmp_path, [feature(square(1.2, 1.2, .2))], aoi=aoi)
    row = result["assets"][0]
    assert row["bbox_candidate"] is True
    assert row["relation"] == "OUTSIDE" and not row["required"]
    assert result["state"] == "BLOCKED"
    assert result["normalized_aoi"] == aoi


def test_concave_bbox_false_positive(tmp_path):
    aoi = {"type":"Polygon", "coordinates":[[[0,0],[4,0],[4,1],[1,1],[1,4],[0,4],[0,0]]]}
    result = plan(tmp_path, [feature(square(2, 2))], aoi=aoi)
    assert result["assets"][0]["relation"] == "OUTSIDE"
    assert result["counts"]["excluded"] == 1


def test_relations_and_conservation(tmp_path):
    result = plan(tmp_path, [feature(square(1,1), "inside"), feature(square(2.5,2.5), "partial"),
        feature(square(3,1), "touch"), feature(square(5,5), "outside"), feature(None, "null"),
        feature({"type":"Point", "coordinates":[1,1]}, "wrong")])
    assert [r["relation"] for r in result["assets"]] == ["FULLY_WITHIN","PARTIAL","TOUCH_ONLY","OUTSIDE","NULL_EMPTY","UNRESOLVED"]
    assert result["counts"] == {"discovered":6,"retained":2,"excluded":2,"unresolved":2,
        "required":2,"cache_valid":0,"fetch_required":2,"blocked_required":0}
    assert result["arithmetic_closed"] and result["state"] == "BLOCKED"


def test_multipolygon_preserved(tmp_path):
    aoi = {"type":"MultiPolygon", "coordinates":[square(0,0)["coordinates"], square(3,3)["coordinates"]]}
    result = plan(tmp_path, [feature(square(3.1,3.1,.1))], aoi=aoi)
    assert result["normalized_aoi"] == aoi
    assert result["assets"][0]["relation"] == "FULLY_WITHIN"


@pytest.mark.parametrize("bad", [None, {}, {"type":"Point", "coordinates":[1,1]},
    {"type":"Polygon", "coordinates":[]},
    {"type":"Polygon", "coordinates":[[[0,0],[2,2],[2,0],[0,2],[0,0]]]},
    {"type":"Polygon", "coordinates":[[[0,0],[1,0],[0,1],[0,2]]]},
    {"type":"Polygon", "coordinates":[[[0,0,1],[1,0,1],[1,1,1],[0,0,1]]]},
    {"type":"Polygon", "coordinates":[[[179,0],[-179,0],[-179,1],[179,0]]]},
    {"type":"FeatureCollection", "features":[]},
    {"type":"FeatureCollection", "features":[feature(square(0,0)),feature(square(2,2))]},
])
def test_bad_geometry_rejected(bad):
    with pytest.raises(ValueError):
        valid_polygon(bad)


def test_unknown_crs_rejected():
    aoi = square(0,0)
    aoi["crs"] = {"type":"name","properties":{"name":"EPSG:26920"}}
    with pytest.raises(ValueError, match="CRS"):
        valid_polygon(aoi)


@pytest.mark.parametrize("number", [float("nan"),float("inf"),True])
def test_nonfinite_or_boolean_coordinates(number):
    aoi = square(0,0)
    aoi["coordinates"][0][1][0] = number
    with pytest.raises(ValueError): valid_polygon(aoi)


def test_unbound_registry_and_empty_do_not_ready(tmp_path):
    for registry in [{}, {"providers":{"dem":{"catalog_path":None}}}, configured(tmp_path,[])]:
        result = build_plan({"aoi":square(0,0)}, registry, tmp_path)
        assert result["state"] == "BLOCKED" and result["unresolved_reasons"]


def test_catalog_mutation_hash_guard(tmp_path):
    registry = configured(tmp_path,[feature(square(1,1))])
    (tmp_path/"tiles.geojson").write_text("{}")
    result = build_plan({"aoi":square(0,0,3)},registry,tmp_path)
    assert result["state"] == "BLOCKED"
    assert "HASH" in result["catalogs"][0]["reason"]


def test_catalog_denominator_mismatch(tmp_path):
    registry = configured(tmp_path,[feature(square(1,1))])
    registry["providers"]["fixture"]["catalog_record_count"] = 0
    result = build_plan({"aoi":square(0,0,3)},registry,tmp_path)
    assert "DENOMINATOR" in result["catalogs"][0]["reason"]


def test_equal_basename_different_identity(tmp_path):
    result = plan(tmp_path,[feature(square(1,1), "a/tile.tif"),feature(square(1,1), "b/tile.tif")])
    keys = [r["asset_key"] for r in result["assets"]]
    assert len(set(keys)) == 2
    assert result["counts"]["cache_valid"] == 0


def test_duplicate_identity_not_dropped(tmp_path):
    result = plan(tmp_path,[feature(square(1,1)),feature(square(1,1))])
    assert result["counts"]["discovered"] == result["counts"]["unresolved"] == 2
    assert result["counts"]["blocked_required"] == 2


def test_missing_url_blocks_required(tmp_path):
    result = plan(tmp_path,[feature(square(1,1), source_url=None)])
    assert result["counts"]["blocked_required"] == 1
    assert result["assets"][0]["source_status"] == "UNRESOLVED"


def test_unknown_date_filter_not_silent_exclusion(tmp_path):
    result = plan(tmp_path,[feature(square(1,1))], filters={"date_from":"2020-01-01"})
    assert result["counts"]["unresolved"] == 1
    assert result["assets"][0]["reasons"] == ["FILTER_ACQUISITION_DATE_UNKNOWN"]


def test_explicit_filter_exclusion_is_counted(tmp_path):
    result = plan(tmp_path,[feature(square(1,1))], filters={"products":["point_cloud"]})
    assert result["counts"]["excluded"] == 1
    assert result["assets"][0]["raw_record"]["properties"]["product"] == "bare_earth_dem"


def test_buffer_does_not_mutate_aoi(tmp_path):
    aoi = square(-66.2,18.2,.01)
    result = plan(tmp_path,[feature(aoi)], aoi=aoi, processing_buffer_m=100)
    assert result["normalized_aoi"] == aoi
    assert result["processing_geometry"] != aoi
    assert result["buffer_method"]["method"] == "UTM20N_planar"


def test_raw_import_bytes_and_edit_lineage(tmp_path):
    raw = json.dumps(square(0,0,3),indent=2)
    result = plan(tmp_path,[feature(square(1,1))], raw_import_text=raw, aoi=square(0,0,4))
    assert result["raw_import"]["text"] == raw
    assert result["raw_import"]["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert result["raw_import"]["edited"]


def test_registry_cannot_escape_root(tmp_path):
    registry = {"providers":{"evil":{"catalog_path":"../tiles.geojson","catalog_type":"geojson"}}}
    result = build_plan({"aoi":square(0,0)}, registry,tmp_path)
    assert "OUTSIDE_REPOSITORY" in result["catalogs"][0]["reason"]


def test_strict_json():
    for raw in [b'{"x":1,"x":2}',b'{"x":NaN}']:
        with pytest.raises(ValueError): strict_json(raw)


def test_endpoint_and_no_fetch_route(tmp_path,monkeypatch):
    registry = configured(tmp_path,[feature(square(1,1))])
    (tmp_path/"configs").mkdir()
    (tmp_path/"configs"/"spatial_dataset_providers.json").write_text(json.dumps(registry))
    monkeypatch.setattr(aoi_api,"ROOT",tmp_path)
    app = FastAPI(); app.include_router(aoi_api.router)
    with TestClient(app) as client:
        response = client.post("/spatial/aoi/plan",json={"aoi":square(0,0,3)})
        assert response.status_code == 200 and response.json()["planning_gate"] == "PASS"
        assert client.post("/spatial/aoi/fetch",json={}).status_code == 404
        assert client.post("/spatial/aoi/plan",json={"aoi":square(0,0),"catalog_path":"/etc/passwd"}).status_code == 422
        assert client.post("/spatial/aoi/plan",content="{}").status_code == 415
        assert client.post("/spatial/aoi/plan",content='{"aoi":NaN}',headers={"Content-Type":"application/json"}).status_code == 422
        assert client.post("/spatial/aoi/plan",content=b"x"*(5*1024*1024+1),headers={"Content-Type":"application/json"}).status_code == 413


def test_wire_schema_matches_ready_and_blocked(tmp_path):
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).resolve().parents[1]/"schemas"/"aoi_acquisition_plan_v1.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for result in [plan(tmp_path,[feature(square(1,1))]), plan(tmp_path,[]),
                   plan(tmp_path,[feature(None)])]:
        validator.validate(json.loads(json.dumps(result)))


def test_main_mount_is_additive():
    import ast
    main = Path(__file__).resolve().parents[1]/"server"/"backend"/"main.py"
    tree = ast.parse(main.read_text())
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
               and n.func.attr == "include_router" and n.args
               and isinstance(n.args[0],ast.Name) and n.args[0].id == "aoi_router"
               for n in ast.walk(tree))
