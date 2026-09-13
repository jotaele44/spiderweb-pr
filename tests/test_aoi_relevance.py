"""Synthetic TEST_ONLY catalog tests; no live-source or coverage certification."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.backend import aoi_api
from server.backend.aoi_planner import build_plan, digest
from server.backend.aoi_relevance import build_recommendations, summarize_plan


def polygon(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w,s],[e,s],[e,n],[w,n],[w,s]]]}


AOI = polygon(-66.2, 18.2, -66.1, 18.3)
INSIDE = polygon(-66.18, 18.22, -66.16, 18.24)
OUTSIDE = polygon(-66.0, 18.2, -65.9, 18.3)
TOUCH = polygon(-66.1, 18.2, -66.0, 18.3)


def feature(asset, geometry=INSIDE, **properties):
    return {"type": "Feature", "geometry": copy.deepcopy(geometry), "properties": {
        "asset_id": asset, "source_url": f"https://example.invalid/{asset}.tif",
        "product": "bare_earth_dem", "size_bytes": 100, "resolution_m": 1,
        "acquisition_date": "2020-01-01", **properties}}


def registry_at(root, catalogs):
    providers = {}
    for dataset, features in catalogs.items():
        path = root / f"{dataset}.geojson"
        raw = json.dumps({"type": "FeatureCollection", "features": features}).encode()
        path.write_bytes(raw)
        providers[dataset] = {
            "label": f"TEST_ONLY {dataset}", "provider_id": f"TEST_ONLY_{dataset}",
            "catalog_type": "geojson", "catalog_path": path.name,
            "catalog_sha256": hashlib.sha256(raw).hexdigest(),
            "catalog_record_count": len(features), "catalog_version": "TEST_ONLY_V1",
            "dataset_class": "bare_earth_dem"}
    return {"providers": providers}


def build(root, catalogs, **kwargs):
    registry = registry_at(root, catalogs)
    return build_recommendations({"aoi": AOI, **kwargs}, registry, root)


def rehash(plan):
    plan.pop("plan_id", None)
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = digest(plan)
    plan["plan_id"] = f"aoi-{plan['plan_sha256']}"
    return plan


def test_two_levels_and_exact_file_ids(tmp_path):
    response = build(tmp_path, {"A": [feature("a"), feature("away", OUTSIDE)],
                                "B": [feature("b")], "C": [feature("outside", OUTSIDE)]})
    assert response["recommended_dataset_ids"] == ["A", "B"]
    assert response["datasets"][0]["applicable_file_row_ids"] == ["A:0"]
    assert response["datasets"][0]["all_row_ids"] == ["A:0", "A:1"]
    assert response["counts"]["datasets_examined"] == 3
    assert response["counts"]["file_rows_examined"] == 4
    assert response["datasets"][2]["recommendation_state"] == "NO_MATCH_IN_SNAPSHOT"


def test_bbox_intersection_inside_hole_not_a_match(tmp_path):
    aoi = copy.deepcopy(AOI)
    aoi["coordinates"].append(polygon(-66.19,18.21,-66.15,18.25)["coordinates"][0])
    registry = registry_at(tmp_path, {"A": [feature("hole")]})
    response = build_recommendations({"aoi": aoi}, registry, tmp_path)
    assert response["plan"]["assets"][0]["bbox_candidate"] is True
    assert response["plan"]["assets"][0]["relation"] == "OUTSIDE"
    assert response["recommended_dataset_ids"] == []
    assert response["plan"]["normalized_aoi"] == aoi


def test_multipart_gap_not_a_match(tmp_path):
    multipart = {"type": "MultiPolygon", "coordinates": [
        polygon(-66.3,18.2,-66.25,18.3)["coordinates"],
        polygon(-66.1,18.2,-66.05,18.3)["coordinates"]]}
    reg = registry_at(tmp_path, {"A": [feature("gap")]})
    result = build_recommendations({"aoi": multipart}, reg, tmp_path)
    assert result["recommended_dataset_ids"] == []
    assert result["plan"]["assets"][0]["bbox_candidate"] is True


def test_touch_is_not_positive_area(tmp_path):
    result = build(tmp_path, {"A": [feature("edge", TOUCH)]})
    assert result["recommended_dataset_ids"] == []
    assert result["plan"]["assets"][0]["relation"] == "TOUCH_ONLY"


def test_partial_overlap_is_relevant(tmp_path):
    result = build(tmp_path, {"A": [feature("partial", polygon(-66.15,18.25,-66.05,18.35))]})
    assert result["recommended_dataset_ids"] == ["A"]
    assert result["plan"]["assets"][0]["relation"] == "PARTIAL"


def test_unbound_catalog_is_not_no_match(tmp_path):
    result = build_recommendations({"aoi": AOI}, {"providers": {"A": {"catalog_path": None}}}, tmp_path)
    assert result["datasets"][0]["recommendation_state"] == "UNRESOLVED"
    assert result["unresolved_dataset_ids"] == ["A"]
    assert result["recommended_dataset_ids"] == []


def test_null_geometry_preserved_as_unresolved(tmp_path):
    result = build(tmp_path, {"A": [feature("unknown", None)]})
    assert result["datasets"][0]["recommendation_state"] == "UNRESOLVED"
    assert result["datasets"][0]["all_row_ids"] == ["A:0"]


def test_one_match_plus_unknown_is_visible_but_incomplete(tmp_path):
    result = build(tmp_path, {"A": [feature("match"), feature("unknown", None)]})
    assert result["recommended_dataset_ids"] == ["A"]
    assert result["unresolved_dataset_ids"] == ["A"]
    assert result["datasets"][0]["file_resolution_state"] == "UNRESOLVED"
    assert result["datasets"][0]["applicable_file_row_ids"] == ["A:0"]


def test_filter_exclusion_not_geographic_absence(tmp_path):
    result = build(tmp_path, {"A": [feature("dem")]}, filters={"products": ["imagery"]})
    item = result["datasets"][0]
    assert item["spatial_relevance"] == "RELEVANT"
    assert item["recommendation_state"] == "FILTERED_OUT"
    assert item["spatial_match_row_ids"] == ["A:0"]
    assert item["applicable_file_row_ids"] == []


def test_unknown_filter_metadata_is_not_no_match(tmp_path):
    result = build(tmp_path, {"A": [feature("undated", acquisition_date=None)]},
                   filters={"date_from": "2019-01-01"})
    assert result["datasets"][0]["recommendation_state"] == "RELEVANT_UNRESOLVED"
    assert result["recommended_dataset_ids"] == []


def test_processing_buffer_not_promoted_to_aoi_match(tmp_path):
    near = polygon(-66.099,18.22,-66.098,18.23)
    result = build(tmp_path, {"A": [feature("near", near)]}, processing_buffer_m=500)
    assert result["recommended_dataset_ids"] == []
    assert result["processing_only_dataset_ids"] == ["A"]
    assert result["datasets"][0]["processing_only_file_row_ids"] == ["A:0"]
    assert result["plan"]["normalized_aoi"] == AOI


def test_sources_and_equal_basenames_not_consolidated(tmp_path):
    result = build(tmp_path, {"A": [feature("same", source_url="https://example.invalid/A/same.tif")],
                                "B": [feature("same", source_url="https://example.invalid/B/same.tif")]})
    assert result["recommended_dataset_ids"] == ["A", "B"]
    assert len({r["asset_key"] for r in result["plan"]["assets"]}) == 2
    assert result["source_equivalence"] == "NOT_INFERRED"
    assert all(d["comparison_relation"] == "UNADJUDICATED" for d in result["datasets"])


def test_same_url_not_independent_or_silently_deduplicated(tmp_path):
    result = build(tmp_path, {"A": [feature("same")], "B": [feature("same")]})
    assert result["recommended_dataset_ids"] == []
    assert result["counts"]["file_rows_examined"] == 2
    assert len(result["unresolved_dataset_ids"]) == 2


def test_empty_snapshot_not_ready(tmp_path):
    result = build(tmp_path, {"A": []})
    assert result["datasets"][0]["recommendation_state"] == "NO_MATCH_IN_SNAPSHOT"
    assert result["plan"]["state"] == "BLOCKED"
    assert result["fetch_enabled"] is False


def test_empty_registry_not_global_completeness(tmp_path):
    result = build_recommendations({"aoi": AOI}, {}, tmp_path)
    assert result["counts"]["datasets_examined"] == 0
    assert result["global_catalog_completeness"] == "UNRESOLVED"
    assert result["plan"]["state"] == "BLOCKED"


def test_no_raw_or_plan_mutation(tmp_path):
    reg = registry_at(tmp_path, {"A": [feature("a")]})
    reg["providers"]["A"]["label"] = "  RAW Accént  "
    plan = build_plan({"aoi": AOI}, reg, tmp_path)
    before = copy.deepcopy(plan)
    result = summarize_plan(plan, reg)
    assert plan == before
    assert result["plan"] == before
    assert result["datasets"][0]["label_raw"] == "  RAW Accént  "
    result["plan"]["assets"].clear()
    assert plan == before


def test_response_hash_covers_everything(tmp_path):
    result = build(tmp_path, {"A": [feature("a")]})
    body = {k:v for k,v in result.items() if k not in {"response_id","response_sha256"}}
    assert digest(body) == result["response_sha256"]
    body["datasets"][0]["recommended"] = False
    assert digest(body) != result["response_sha256"]


@pytest.mark.parametrize("mutation", ["row_loss", "counter", "duplicate_row", "orphan",
                                      "duplicate_catalog", "required_touch", "required_excluded",
                                      "boolean_counter", "unknown_relation"])
def test_rehashed_corrupt_plan_rejected(tmp_path, mutation):
    reg = registry_at(tmp_path, {"A": [feature("a")]})
    plan = build_plan({"aoi": AOI}, reg, tmp_path)
    row = plan["assets"][0]
    if mutation == "row_loss": plan["assets"].clear()
    elif mutation == "counter": plan["counts"]["discovered"] += 1
    elif mutation == "duplicate_row": plan["assets"].append(copy.deepcopy(row))
    elif mutation == "orphan": row["dataset_id"] = "NOT_REGISTERED"
    elif mutation == "duplicate_catalog": plan["catalogs"].append(copy.deepcopy(plan["catalogs"][0]))
    elif mutation == "required_touch": row["processing_relation"] = "TOUCH_ONLY"
    elif mutation == "required_excluded": row["disposition"] = "EXCLUDED"
    elif mutation == "boolean_counter": plan["counts"]["discovered"] = True
    elif mutation == "unknown_relation": row["relation"] = "GUESS"
    with pytest.raises(ValueError): summarize_plan(rehash(plan), reg)


def test_wrong_registry_rejected(tmp_path):
    reg = registry_at(tmp_path, {"A": [feature("a")]})
    plan = build_plan({"aoi": AOI}, reg, tmp_path)
    reg["providers"]["A"]["label"] = "Changed"
    with pytest.raises(ValueError, match="registry snapshot changed"): summarize_plan(plan, reg)


def test_bad_plan_hash_rejected(tmp_path):
    reg = registry_at(tmp_path, {"A": [feature("a")]})
    plan = build_plan({"aoi": AOI}, reg, tmp_path)
    plan["assets"][0]["asset_id"] = "wrong"
    with pytest.raises(ValueError, match="hash mismatch"): summarize_plan(plan, reg)


def test_missing_url_is_relevant_unresolved(tmp_path):
    result = build(tmp_path, {"A": [feature("a", source_url=None)]})
    assert result["datasets"][0]["recommendation_state"] == "RELEVANT_UNRESOLVED"
    assert result["recommended_dataset_ids"] == []


def test_unknown_bytes_not_zero_estimate(tmp_path):
    result = build(tmp_path, {"A": [feature("a", size_bytes=None)]})
    assert result["datasets"][0]["unknown_applicable_sizes"] == 1
    assert result["datasets"][0]["known_applicable_bytes"] == 0


@pytest.mark.parametrize("injected", [{"bbox":[0,0,1,1]}, {"catalog_path":"evil"},
                                       {"source_url":"http://127.0.0.1"}, {"plan": {}}])
def test_no_caller_source_or_bbox_injection(tmp_path, injected):
    with pytest.raises(ValueError): build_recommendations({"aoi": AOI, **injected}, {}, tmp_path)


def test_api_both_routes_and_missing_fetch(tmp_path, monkeypatch):
    reg = registry_at(tmp_path, {"A": [feature("a")]})
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/spatial_dataset_providers.json").write_text(json.dumps(reg))
    monkeypatch.setattr(aoi_api, "ROOT", tmp_path)
    app = FastAPI(); app.include_router(aoi_api.router)
    with TestClient(app) as client:
        res = client.post("/spatial/aoi/recommendations", json={"aoi": AOI})
        assert res.status_code == 200
        assert res.headers["cache-control"] == "no-store"
        assert res.json()["recommended_dataset_ids"] == ["A"]
        legacy = client.post("/spatial/aoi/plan", json={"aoi": AOI})
        assert legacy.status_code == 200
        assert legacy.json()["schema_version"] == "aoi_acquisition_plan.v1.1"
        assert "datasets" not in legacy.json()
        assert client.post("/spatial/aoi/fetch", json={}).status_code == 404
        assert client.post("/spatial/aoi/recommendations", content="{}").status_code == 415
        assert client.post("/spatial/aoi/recommendations", json={"aoi": None}).status_code == 422


def test_all_geometry_and_catalog_states_close(tmp_path):
    reg = registry_at(tmp_path, {"A": [feature("yes"), feature("no",OUTSIDE), feature("edge",TOUCH)],
                               "B": [feature("unknown",None)], "C": []})
    reg["providers"]["D"] = {"catalog_path": None}
    result = build_recommendations({"aoi": AOI}, reg, tmp_path)
    assert sum(result["counts"]["dataset_states"].values()) == 4
    ids = [i for d in result["datasets"] for i in d["all_row_ids"]]
    assert len(ids) == len(set(ids)) == len(result["plan"]["assets"]) == 4
    assert result["coverage_state"] == "UNKNOWN"
    assert result["certification"] == "OPEN"
