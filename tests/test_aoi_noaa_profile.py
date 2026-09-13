"""Optional STAC fields: exact links and URL membership, never name inference."""
import copy
import pytest
from server.backend.aoi_catalog_snapshot import convert_snapshot
from server.backend.aoi_planner import canonical_bytes

BASE = 'https://example.invalid/dataset/'
GEOM = {'type':'Polygon','coordinates':[[[-66.2,18.2],[-66.1,18.2],[-66.1,18.3],[-66.2,18.3],[-66.2,18.2]]]}

def fixture():
    self_url=BASE+'stac/item.json'
    spec={'dataset_id':'TEST_ONLY','provider_id':'TEST_ONLY','dataset_class':'bare_earth_dem',
          'collection_id_raw':'TEST_ONLY_COLLECTION','collection_url':BASE+'stac/collection.json',
          'items_url':BASE+'stac/items.json','urls_url':BASE+'urls.txt',
          'approved_url_prefixes':[BASE],'data_suffixes':['.tif'],'data_asset_keys':[],
          'source_profile':'noaa_cog_single_asset_v1'}
    collection={'type':'Collection','id':'TEST_ONLY_COLLECTION','links':[{'rel':'item','href':self_url}]}
    asset={'href':BASE+'tile.tif','type':'image/tiff; application=geotiff; profile=cloud-optimized',
           'proj:shape':[10,10],'proj:transform':[1,0,0,0,-1,0],'proj:epsg':6566}
    item={'type':'Feature','id':'source-id-not-the-filename','stac_version':'1.1.0','geometry':copy.deepcopy(GEOM),
          'properties':{'datetime':None},'links':[{'rel':'self','href':self_url}],
          'assets':{'opaque-asset-key':asset}}
    items={'type':'FeatureCollection','features':[item]}
    return collection,items,BASE+'tile.tif\n',spec


def convert(c,i,u,s):
    return convert_snapshot(canonical_bytes(c),canonical_bytes(i),u.encode(),s)


def test_optional_fields_bind_via_exact_links_mime_grid_and_url():
    c,i,u,s=fixture();before=copy.deepcopy(i)
    cat,receipt=convert(c,i,u,s)
    assert i==before and 'collection' not in i['features'][0]
    row=cat['features'][0]['properties']
    assert row['asset_id']=='["source-id-not-the-filename","opaque-asset-key"]'
    assert row['collection_binding_basis']=='EXACT_COLLECTION_ITEM_LINK_AND_ITEM_SELF_LINK'
    assert row['data_binding_basis']=='SINGLE_COG_MEDIA_GRID_AND_EXACT_PUBLISHED_URL'
    assert receipt['source_profile']=='noaa_cog_single_asset_v1'
    assert receipt['data_url_relation']['SYMMETRIC_DIFFERENCE']==[]


@pytest.mark.parametrize('mutation',['profile_missing','profile_unknown','explicit_wrong_collection','explicit_null_collection',
    'foreign_collection_link','unlinked_self','wrong_media','no_shape','boolean_shape','singular_transform',
    'nonfinite_transform','boolean_transform','unknown_epsg','missing_url','extra_asset','explicit_thumbnail_role',
    'explicit_empty_roles','wrong_bottom_matrix_row'])
def test_optional_field_policy_fails_closed(mutation):
    c,i,u,s=fixture();item=i['features'][0];asset=item['assets']['opaque-asset-key']
    if mutation=='profile_missing':s.pop('source_profile')
    elif mutation=='profile_unknown':s['source_profile']='trust_names'
    elif mutation=='explicit_wrong_collection':item['collection']='OTHER'
    elif mutation=='explicit_null_collection':item['collection']=None
    elif mutation=='foreign_collection_link':item['links'].append({'rel':'collection','href':BASE+'different.json'})
    elif mutation=='unlinked_self':item['links'][0]['href']=BASE+'same-name-other-item.json'
    elif mutation=='wrong_media':asset['type']='image/png'
    elif mutation=='no_shape':asset.pop('proj:shape')
    elif mutation=='boolean_shape':asset['proj:shape']=[True,10]
    elif mutation=='singular_transform':asset['proj:transform']=[0,0,0,0,0,0]
    elif mutation=='nonfinite_transform':asset['proj:transform']=[float('nan'),0,0,0,-1,0]
    elif mutation=='boolean_transform':asset['proj:transform']=[True,0,0,0,-1,0]
    elif mutation=='unknown_epsg':asset['proj:epsg']=None
    elif mutation=='missing_url':u=''
    elif mutation=='extra_asset':item['assets']['other']=copy.deepcopy(asset)
    elif mutation=='explicit_thumbnail_role':asset['roles']=['thumbnail']
    elif mutation=='explicit_empty_roles':asset['roles']=[]
    elif mutation=='wrong_bottom_matrix_row':asset['proj:transform']=[1,0,0,0,-1,0,0,1,1]
    with pytest.raises(ValueError):convert(c,i,u,s)


def test_explicit_collection_conflict_never_overridden():
    c,i,u,s=fixture();i['features'][0]['collection']='WRONG'
    with pytest.raises(ValueError,match='COLLECTION_BINDING_MISMATCH'):convert(c,i,u,s)


def test_nine_element_affine_grid_supported():
    c,i,u,s=fixture();i['features'][0]['assets']['opaque-asset-key']['proj:transform'] += [0,0,1]
    cat,_=convert(c,i,u,s)
    assert len(cat['features'])==1


def duplicate_fixture():
    c,i,u,s=fixture()
    extra=copy.deepcopy(i['features'][0])
    extra['links'][0]['href']=BASE+'second-block/same-item.json'
    extra['assets']['opaque-asset-key']['href']=BASE+'second-block/tile.tif'
    c['links'].append({'rel':'item','href':extra['links'][0]['href']})
    i['features'].append(extra);u+=extra['assets']['opaque-asset-key']['href']+'\n'
    return c,i,u,s


def test_duplicate_raw_ids_retained_with_unique_exact_self_bindings():
    c,i,u,s=duplicate_fixture();s['item_identity_scope']='collection_linked_self_url'
    cat,receipt=convert(c,i,u,s)
    assert len(cat['features'])==2
    assert len({x['properties']['asset_id'] for x in cat['features']})==2
    assert len({x['properties']['source_item_id_raw'] for x in cat['features']})==1
    assert receipt['raw_item_id_status']=='NONCANONICAL_DUPLICATE_IDS'
    assert receipt['raw_item_id_collision_groups']==1
    assert receipt['raw_item_id_collision_rows']==2
    assert len(receipt['raw_item_id_collisions']['source-id-not-the-filename'])==2


def test_duplicate_raw_ids_without_qualified_policy_still_block():
    with pytest.raises(ValueError,match='DUPLICATE_ITEM_ID'):
        convert(*duplicate_fixture())


def test_qualified_policy_does_not_allow_duplicate_self_urls():
    c,i,u,s=duplicate_fixture();s['item_identity_scope']='collection_linked_self_url'
    i['features'][1]['links'][0]['href']=i['features'][0]['links'][0]['href']
    with pytest.raises(ValueError,match='DUPLICATE_ITEM_SELF_LINK'):
        convert(c,i,u,s)


def test_qualified_policy_does_not_allow_duplicate_data_urls():
    c,i,u,s=duplicate_fixture();s['item_identity_scope']='collection_linked_self_url'
    i['features'][1]['assets']['opaque-asset-key']['href']=BASE+'tile.tif'
    with pytest.raises(ValueError):convert(c,i,u,s)


def test_unknown_scope_cannot_promote_duplicate_ids():
    c,i,u,s=duplicate_fixture();s['item_identity_scope']='filename_only'
    with pytest.raises(ValueError,match='UNKNOWN_ITEM_IDENTITY_SCOPE'):
        convert(c,i,u,s)


def test_changed_converter_gets_new_derivative_not_rewritten_snapshot(tmp_path, monkeypatch):
    from server.backend import aoi_catalog_snapshot as adapter
    import json
    c,i,u,s=fixture();s.update(original_producer='TEST_ONLY',label_raw='TEST_ONLY')
    raw={'collection.raw.json':canonical_bytes(c),'items.raw.json':canonical_bytes(i),'urls.raw.txt':u.encode()}
    monkeypatch.setattr(adapter,'acquire_metadata',lambda url,directory,name,prefixes:(raw[name],{'url':url}))
    monkeypatch.setattr(adapter,'converter_manifest',lambda:{'code':'v1'})
    a=adapter.freeze_catalog(s,tmp_path/'work',tmp_path)['providers']['TEST_ONLY']
    old=(tmp_path/a['source_manifest_path']).read_bytes()
    monkeypatch.setattr(adapter,'converter_manifest',lambda:{'code':'v2'})
    b=adapter.freeze_catalog(s,tmp_path/'work',tmp_path)['providers']['TEST_ONLY']
    assert a['catalog_path']!=b['catalog_path']
    assert (tmp_path/a['source_manifest_path']).read_bytes()==old
    ma=json.loads(old);mb=json.loads((tmp_path/b['source_manifest_path']).read_text())
    assert ma['source_snapshot_id']==mb['source_snapshot_id']
    assert ma['input_hashes']==mb['input_hashes']
    assert ma['catalog_sha256']==mb['catalog_sha256']
