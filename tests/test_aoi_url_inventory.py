"""Synthetic mixed manifests patterned on observed NOAA structure, not NOAA raw bytes."""
import copy
import hashlib
import json
import pytest
pytest.importorskip("pyproj", reason="GIS-equipped suite required; skip is not PASS")
from server.backend import aoi_catalog_snapshot as adapter
from server.backend.aoi_planner import canonical_bytes
from server.backend.aoi_url_inventory import UrlInventoryError, audit_url_inventory
from server.backend.aoi_relevance import build_recommendations

BASE = "https://example.invalid/dem/test/"
GEO = {"type": "Polygon", "coordinates": [[[-66.2,18.2],[-66.1,18.2],[-66.1,18.3],[-66.2,18.3],[-66.2,18.2]]]}
SPEC = {"dataset_id":"TEST_ONLY", "provider_id":"TEST_ONLY", "original_producer":"TEST_ONLY",
        "label_raw":" TEST_ONLY raw label ", "dataset_class":"bare_earth_dem", "collection_id_raw":"source_imagery_id_raw",
        "collection_url":BASE+"stac/collection.json", "items_url":BASE+"stac/items.json",
        "urls_url":BASE+"urls.txt", "catalog_url":BASE+"stac/catalog.json",
        "approved_url_prefixes":[BASE], "data_suffixes":[".tif"], "data_asset_keys":[],
        "url_list_auxiliaries":[{"url":BASE+"meta.xml", "role":"metadata", "evidence_url":BASE+"index.html", "basis":"TEST_ONLY exact published link"}]}
DATA = [BASE+"tile.tif"]
ITEMS = [BASE+"stac/item.json"]
STRUCTURAL = [SPEC[k] for k in ("collection_url","items_url","urls_url","catalog_url")]


def audit(lines, **overrides):
    args=dict(data_urls=DATA,item_urls=ITEMS,structural_urls=STRUCTURAL,
              auxiliary_bindings=SPEC["url_list_auxiliaries"],approve=lambda u: adapter.approved_url(u,[BASE]))
    args.update(overrides)
    return audit_url_inventory(lines, **args)


def docs(mixed=True):
    c={"type":"Collection","id":SPEC["collection_id_raw"],"links":[{"rel":"item","href":ITEMS[0]}]}
    item={"type":"Feature","stac_version":"1.1.0","id":"ID1","collection":c["id"],"geometry":copy.deepcopy(GEO),
          "properties":{"datetime":"2020-01-01T00:00:00Z"},"links":[{"rel":"self","href":ITEMS[0]}],
          "assets":{"data":{"href":DATA[0],"roles":["data"]}}}
    lines=DATA+ITEMS+STRUCTURAL+[BASE+"meta.xml"] if mixed else DATA
    return canonical_bytes(c),canonical_bytes({"type":"FeatureCollection","features":[item]}),("\n".join(lines)+"\n").encode()


def test_data_and_metadata_are_not_all_counted_as_tiles():
    raw=docs()[2]; r=audit(raw)
    assert r["state"]=="PASS"
    assert r["counts"]=={"lines":7,"DATA":1,"ITEM_METADATA":1,"CATALOG_METADATA":4,"DECLARED_AUXILIARY":1,"BLANK":0,"UNRESOLVED":0}
    assert r["data_url_relation"]["INTERSECTION"]==DATA
    assert r["data_url_relation"]["SYMMETRIC_DIFFERENCE"]==[]


def test_blank_bom_crlf_and_raw_lines_preserved():
    raw=b'\xef\xbb\xbf'+(DATA[0]+"\r\n\r\n").encode();r=audit(raw)
    assert r["input_has_utf8_bom"] is True
    assert r["rows"][0]["raw_line"]==DATA[0]+"\r\n"
    assert r["counts"]["BLANK"]==1
    assert r["arithmetic_closed"] is True


def test_legacy_data_only_inventory_still_closes():
    r=audit(docs(False)[2]);assert r["state"]=="PASS"
    assert r["item_metadata_relation"]["A_ONLY"]==ITEMS
    assert r["item_metadata_list_presence_required"] is False


@pytest.mark.parametrize("unknown",[BASE+"extra.tif", BASE+"unknown.json",BASE+"unknown.xml",BASE+"stac/not-an-item.json",BASE+"other.zip"])
def test_suffix_and_proximity_cannot_justify_dropping_unknown_rows(unknown):
    with pytest.raises(UrlInventoryError) as caught: audit(docs()[2]+(unknown+"\n").encode())
    report=caught.value.report
    assert len(report["rows"])==8 and report["rows"][-1]["url_raw"]==unknown
    assert report["counts"]["UNRESOLVED"]==1 and report["state"]=="BLOCKED"


@pytest.mark.parametrize("which",[DATA[0],ITEMS[0],STRUCTURAL[0],BASE+"meta.xml"])
def test_duplicate_data_or_metadata_is_never_silently_deduplicated(which):
    with pytest.raises(UrlInventoryError) as caught:audit(docs()[2]+(which+"\n").encode())
    assert caught.value.report["duplicate_urls"]=={which:2}
    assert caught.value.report["counts"]["UNRESOLVED"]==2


def test_missing_data_survives_as_set_difference():
    with pytest.raises(UrlInventoryError) as caught:audit(("\n".join(ITEMS+STRUCTURAL)+"\n").encode())
    assert caught.value.report["data_url_relation"]["A_ONLY"]==DATA


def test_data_cannot_be_reclassified_as_auxiliary():
    binding={"url":DATA[0],"role":"metadata","evidence_url":BASE+"index.html","basis":"incorrect"}
    with pytest.raises(UrlInventoryError) as caught:audit(docs()[2],auxiliary_bindings=[*SPEC["url_list_auxiliaries"],binding])
    assert any("DATA_SUFFIX_CANNOT_BE_DECLARED_AUXILIARY" in r for r in caught.value.report["blockers"])


@pytest.mark.parametrize("change",[{"role":"ignore"},{"evidence_url":None},{"basis":""},{"evidence_url":"http://invalid.example"}])
def test_unbound_auxiliary_declaration_blocks(change):
    binding=SPEC["url_list_auxiliaries"][0]|change
    with pytest.raises(UrlInventoryError):audit(docs()[2],auxiliary_bindings=[binding])


@pytest.mark.parametrize("url",[BASE+"../evil.xml",BASE+"%2e%2e/evil.xml", "https://evil.invalid/meta.xml", " "+DATA[0],DATA[0]+"?key=x"])
def test_unsafe_inventory_urls_remain_visible(url):
    with pytest.raises(UrlInventoryError) as caught:audit(docs()[2]+(url+"\n").encode())
    assert caught.value.report["rows"][-1]["state"]=="UNRESOLVED"
    assert caught.value.report["rows"][-1]["url_raw"]==url


def test_invalid_utf8_not_silently_replaced():
    with pytest.raises(UnicodeDecodeError):audit(b'\xff')


def test_duplicate_expected_data_binding_blocks():
    with pytest.raises(UrlInventoryError):audit(docs()[2],data_urls=DATA+DATA)


def test_collection_structural_alias_cannot_silently_hide_data():
    with pytest.raises(UrlInventoryError):audit(docs()[2],structural_urls=STRUCTURAL+DATA)


def test_conversion_and_exact_relevance_only_emit_data(tmp_path):
    raw=docs();catalog,receipt=adapter.convert_snapshot(*raw,SPEC)
    assert len(catalog["features"])==1 and receipt["url_inventory"]["counts"]["lines"]==7
    payload=canonical_bytes(catalog);(tmp_path/"catalog.json").write_bytes(payload)
    reg={"providers":{"TEST_ONLY":{"provider_id":"TEST_ONLY","catalog_type":"geojson","catalog_path":"catalog.json",
          "catalog_sha256":hashlib.sha256(payload).hexdigest(),"catalog_record_count":1,"catalog_version":"TEST_ONLY"}}}
    result=build_recommendations({"aoi":GEO},reg,tmp_path)
    assert result["recommended_dataset_ids"]==["TEST_ONLY"]
    assert result["datasets"][0]["applicable_file_row_ids"]==["TEST_ONLY:0"]
    assert len(result["plan"]["assets"])==1 and result["fetch_enabled"] is False


def test_failed_freeze_preserves_diagnostic_and_no_catalog(tmp_path,monkeypatch):
    c,i,u=docs();u+=(BASE+"unclassified.xml\n").encode()
    raw={"collection.raw.json":c,"items.raw.json":i,"urls.raw.txt":u}
    monkeypatch.setattr(adapter,"acquire_metadata",lambda url,directory,name,prefixes:(raw[name],{"url":url,"kind":"TEST_ONLY"}))
    for _ in range(2):
        with pytest.raises(UrlInventoryError):adapter.freeze_catalog(SPEC,tmp_path/"work",tmp_path)
    files=list((tmp_path/"work").glob('url-inventory-blocked-*.json'))
    assert len(files)==1 and not (tmp_path/"registry").exists()
    report=json.loads(files[0].read_text())
    assert report["audit"]["counts"]["lines"]==8
    assert report["input_hashes"]["urls"]==hashlib.sha256(u).hexdigest()


def test_same_basename_different_paths_is_not_a_data_match():
    raw=(BASE+"different/tile.tif\n").encode()
    with pytest.raises(UrlInventoryError) as caught:audit(raw)
    assert caught.value.report["data_url_relation"]["A_ONLY"]==DATA
    assert caught.value.report["rows"][0]["state"]=="UNRESOLVED"


def test_registry_auxiliary_bindings_do_not_activate_live_catalogs():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    sources=json.loads((root/"configs/aoi_catalog_sources.json").read_text())["sources"]
    m9101=sources["NOAA_OCM_m9101"]
    assert len(m9101["url_list_auxiliaries"])==8
    assert m9101["state"]=="DISCOVERED_UNBOUND"
    assert any("PeurtoRico" in r["url"] for r in m9101["url_list_auxiliaries"])


def test_extra_data_url_is_a_candidate_not_identity():
    unknown=BASE+"different/tile.tif"
    with pytest.raises(UrlInventoryError) as caught:audit(docs()[2]+(unknown+"\n").encode())
    assert caught.value.report["data_url_relation"]["B_ONLY"]==[unknown]
    assert caught.value.report["rows"][-1]["state"]=="UNRESOLVED"


def test_auxiliary_cannot_hide_data_missing_from_stac():
    binding={"url":BASE+"unlisted.tif","role":"metadata","evidence_url":BASE+"index.html","basis":"incorrect"}
    with pytest.raises(UrlInventoryError) as caught:audit(docs()[2],auxiliary_bindings=[binding])
    assert any("DATA_SUFFIX_CANNOT_BE_DECLARED_AUXILIARY" in r for r in caught.value.report["blockers"])
