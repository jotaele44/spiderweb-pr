"""Synthetic adapter regression scope. No claims about unacquired NOAA bytes."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
pytest.importorskip("pyproj", reason="GIS-equipped AOI tests required; skip is not PASS")
from server.backend import aoi_catalog_snapshot as adapter
from server.backend.aoi_planner import canonical_bytes
from server.backend.aoi_relevance import build_recommendations

BASE = "https://example.invalid/dem/test/"
GEOM = {"type":"Polygon", "coordinates":[[[-66.2,18.2],[-66.1,18.2],[-66.1,18.3],[-66.2,18.3],[-66.2,18.2]]]}
SPEC = {"dataset_id":"TEST_ONLY", "provider_id":"TEST_ONLY", "original_producer":"TEST_ONLY",
        "label_raw":" TEST_ONLY raw label ", "dataset_class":"bare_earth_dem", "collection_id_raw":"source_imagery_id_raw",
        "collection_url":BASE+"stac/collection.json", "items_url":BASE+"stac/items.json",
        "urls_url":BASE+"urls.txt", "approved_url_prefixes":[BASE], "data_suffixes":[".tif"], "data_asset_keys":[]}


def source_docs():
    self_url = BASE+"stac/item.json"
    collection = {"type":"Collection", "id":SPEC["collection_id_raw"], "links":[{"rel":"item", "href":self_url}]}
    item = {"type":"Feature", "stac_version":"1.1.0", "id":"ID_1", "collection":collection["id"],
            "geometry":copy.deepcopy(GEOM), "properties":{"datetime":"2021-01-01T00:00:00Z"},
            "links":[{"rel":"self", "href":self_url}],
            "assets":{"data":{"href":BASE+"tile.tif", "roles":["data"], "file:size":10},
                      "metadata":{"href":BASE+"meta.xml", "roles":["metadata"]}}}
    return collection, {"type":"FeatureCollection", "features":[item]}, BASE+"tile.tif\n"


def convert(c, i, u, spec=SPEC):
    return adapter.convert_snapshot(canonical_bytes(c), canonical_bytes(i), u.encode(), spec)


def test_exact_source_binding_and_preserved_fields():
    c,i,u = source_docs(); before = copy.deepcopy(i)
    result, receipt = convert(c,i,u)
    assert i == before
    row = result["features"][0]
    assert row["geometry"] == GEOM
    assert row["properties"]["asset_id"] == '["ID_1","data"]'
    assert row["properties"]["source_item_id_raw"] == "ID_1"
    assert row["properties"]["acquisition_date"] is None
    assert row["properties"]["resolution_m"] is None
    assert receipt["auxiliary_assets"] == 1
    assert receipt["data_assets"] == 1
    assert receipt["collection_id_raw"] == "source_imagery_id_raw"
    for key in ("collection_item_relation", "data_url_relation"):
        assert receipt[key]["A_ONLY"] == receipt[key]["B_ONLY"] == receipt[key]["SYMMETRIC_DIFFERENCE"] == []
        assert receipt[key]["INTERSECTION"] == receipt[key]["UNION"]
    assert receipt["catalog_sha256"] == hashlib.sha256(canonical_bytes(result)).hexdigest()


@pytest.mark.parametrize("mutation", ["wrong_collection", "wrong_item_collection", "missing_self", "missing_item_link",
    "duplicate_item", "duplicate_self", "next", "child", "unknown_role", "no_data", "unsafe_url", "wrong_suffix",
    "boolean_size", "extra_url", "missing_url", "duplicate_url", "returned_mismatch", "no_id", "unsupported_version"])
def test_invalid_catalog_fails_closed(mutation):
    c,i,u = source_docs(); item=i["features"][0]
    if mutation == "wrong_collection": c["id"]="other"
    elif mutation == "wrong_item_collection": item["collection"]="other"
    elif mutation == "missing_self": item["links"]=[]
    elif mutation == "missing_item_link": c["links"]=[]
    elif mutation == "duplicate_item": i["features"].append(copy.deepcopy(item))
    elif mutation == "duplicate_self": item["links"].append(copy.deepcopy(item["links"][0]))
    elif mutation == "next": i["links"]=[{"rel":"next","href":BASE+"next.json"}]
    elif mutation == "child": c["links"].append({"rel":"child","href":BASE+"child.json"})
    elif mutation == "unknown_role": item["assets"]["metadata"]["roles"]=[]
    elif mutation == "no_data": del item["assets"]["data"]
    elif mutation == "unsafe_url": item["assets"]["data"]["href"]="http://127.0.0.1/file.tif"
    elif mutation == "wrong_suffix": item["assets"]["data"]["href"]=BASE+"file.jpg"
    elif mutation == "boolean_size": item["assets"]["data"]["file:size"]=True
    elif mutation == "extra_url": u+=BASE+"extra.tif\n"
    elif mutation == "missing_url": u=""
    elif mutation == "duplicate_url": u+=u
    elif mutation == "returned_mismatch": i["numberReturned"]=0
    elif mutation == "no_id": del item["id"]
    elif mutation == "unsupported_version": item["stac_version"]="2.0.0"
    with pytest.raises(ValueError): convert(c,i,u)


@pytest.mark.parametrize("url", ["http://example.invalid/dem/test/a.tif", "https://example.invalid.evil/dem/test/a.tif",
    "https://example.invalid/dem/other/a.tif", "https://user@example.invalid/dem/test/a.tif", BASE+"a.tif?secret=x",
    BASE+"../a.tif", BASE+"%2e%2e/a.tif", BASE+"a.tif#x", BASE+"a\\b.tif", BASE+"a\nb.tif"])
def test_url_boundary(url):
    with pytest.raises(ValueError): adapter.approved_url(url,[BASE])


def test_null_geometry_not_replaced_by_bbox(tmp_path):
    c,i,u=source_docs(); i["features"][0]["geometry"]=None
    i["features"][0]["bbox"]=[-66.2,18.2,-66.1,18.3]
    catalog,_=convert(c,i,u)
    raw=canonical_bytes(catalog); (tmp_path/"catalog.geojson").write_bytes(raw)
    reg={"providers":{"TEST_ONLY":{"provider_id":"TEST_ONLY","catalog_type":"geojson", "catalog_path":"catalog.geojson",
         "catalog_sha256":hashlib.sha256(raw).hexdigest(),"catalog_record_count":1,"catalog_version":"TEST_ONLY"}}}
    response=build_recommendations({"aoi":GEOM},reg,tmp_path)
    assert response["recommended_dataset_ids"] == []
    assert response["unresolved_dataset_ids"] == ["TEST_ONLY"]
    assert response["plan"]["assets"][0]["relation"] == "NULL_EMPTY"


def test_multiple_data_assets_need_individual_footprints():
    c,i,u=source_docs(); item=i["features"][0]
    item["assets"]["second"]={"href":BASE+"second.tif","roles":["data"]}; u+=BASE+"second.tif\n"
    with pytest.raises(ValueError,match="MULTIPLE_DATA_ASSETS"):
        convert(c,i,u)


def test_same_data_url_is_not_silently_deduplicated():
    c,i,u=source_docs(); item=i["features"][0]
    item["assets"]["second"]=copy.deepcopy(item["assets"]["data"])
    with pytest.raises(ValueError,match="MULTIPLE_DATA_ASSETS|REPEATED_ASSET_URL"): convert(c,i,u)


def test_frozen_outputs_and_resolver_end_to_end(tmp_path, monkeypatch):
    c,i,u=source_docs(); docs={"collection.raw.json":canonical_bytes(c),"items.raw.json":canonical_bytes(i),"urls.raw.txt":u.encode()}
    calls=[]
    def acquire(url, directory, name, prefixes):
        calls.append(name); return docs[name], {"url":url,"sha256":hashlib.sha256(docs[name]).hexdigest(),"acquisition_kind":"TEST_ONLY"}
    monkeypatch.setattr(adapter,"acquire_metadata",acquire)
    proposal=adapter.freeze_catalog(SPEC,tmp_path/"work",tmp_path)
    provider=proposal["providers"]["TEST_ONLY"]
    assert not (tmp_path/"configs/spatial_dataset_providers.json").exists()
    assert provider["label"] == SPEC["label_raw"]
    response=build_recommendations({"aoi":GEOM},proposal,tmp_path)
    assert response["recommended_dataset_ids"] == ["TEST_ONLY"]
    assert response["datasets"][0]["applicable_file_row_ids"] == ["TEST_ONLY:0"]
    assert response["fetch_enabled"] is False
    assert adapter.freeze_catalog(SPEC,tmp_path/"work",tmp_path) == proposal
    root=tmp_path/Path(provider["catalog_path"]).parent
    assert (root/"items.raw.json").read_bytes() == docs["items.raw.json"]


def test_write_once_reuses_or_fails_without_mutation(tmp_path):
    path=tmp_path/"snapshot"
    adapter.write_once(path,b"original"); adapter.write_once(path,b"original")
    with pytest.raises(ValueError,match="IMMUTABLE"): adapter.write_once(path,b"different")
    assert path.read_bytes()==b"original"


def test_corrupt_cached_source_rejected_without_network(tmp_path, monkeypatch):
    path=tmp_path/"items.raw.json"; path.write_bytes(b"wrong")
    (tmp_path/"items.raw.json.receipt.json").write_text(json.dumps({"url":SPEC["items_url"],"sha256":"0"*64}))
    def no_network(*args): raise AssertionError("network must not be retried")
    monkeypatch.setattr(adapter,"build_opener",no_network)
    with pytest.raises(ValueError,match="PRIOR_SNAPSHOT_MISMATCH"):
        adapter.acquire_metadata(SPEC["items_url"],tmp_path,path.name,[BASE])


def test_valid_cached_source_reused_without_network(tmp_path, monkeypatch):
    raw=b'{}'; name="collection.raw.json"; (tmp_path/name).write_bytes(raw)
    (tmp_path/(name+".receipt.json")).write_text(json.dumps({"url":SPEC["collection_url"],"sha256":hashlib.sha256(raw).hexdigest()}))
    monkeypatch.setattr(adapter,"build_opener",lambda *args: (_ for _ in ()).throw(AssertionError("network forbidden")))
    result,_=adapter.acquire_metadata(SPEC["collection_url"],tmp_path,name,[BASE])
    assert result==raw


def test_set_differences_are_explicit():
    result=adapter.relation_sets(["a","b"],["b","c"])
    assert result=={"INTERSECTION":["b"],"A_ONLY":["a"],"B_ONLY":["c"],"UNION":["a","b","c"],"SYMMETRIC_DIFFERENCE":["a","c"]}


@pytest.mark.parametrize("where", ["collection", "items", "item"])
def test_no_silent_crs_discard(where):
    c,i,u=source_docs()
    target={"collection":c,"items":i,"item":i["features"][0]}[where]
    target["crs"]={"properties":{"name":"EPSG:26920"}}
    with pytest.raises(ValueError,match="CRS_MEMBER"): convert(c,i,u)


def test_asset_specific_geometry_not_replaced_by_item_footprint():
    c,i,u=source_docs(); i["features"][0]["assets"]["data"]["proj:geometry"]=GEOM
    with pytest.raises(ValueError,match="PER_ASSET_GEOMETRY"): convert(c,i,u)


def test_registered_sources_with_missing_snapshots_do_not_auto_recommend():
    root=Path(__file__).resolve().parents[1]
    configured=json.loads((root/"configs/spatial_dataset_providers.json").read_text())
    ids={"NOAA_OCM_m9101","NOAA_OCM_m8571"}
    reg={"providers":{key:copy.deepcopy(configured["providers"][key]) for key in ids}}
    for provider in reg["providers"].values():
        provider["catalog_path"]=None
    response=build_recommendations({"aoi":GEOM},reg,root)
    assert set(response["unresolved_dataset_ids"]) == ids
    assert not response["recommended_dataset_ids"]
    assert not response["plan"]["assets"]
    assert response["fetch_enabled"] is False
