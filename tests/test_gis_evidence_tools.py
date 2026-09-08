"""Synthetic parser/benchmark preflight controls, not real layer benchmarks."""
import struct
import pytest
from tools.gis_evidence.cousub import parse_dbf
from tools.gis_evidence.core import digest, checked_bytes, load_geojson, write_new
from tools.gis_evidence.delivery_benchmark import preflight, tile_xy, measured_summary


def dbf(rows):
    # Two explicitly typed CHAR fields, neither names nor geometry.
    h=bytearray(32);h[0]=3;struct.pack_into('<IHH',h,4,len(rows),97,13)
    for name,width in [('GEOID',10),('LSADC',2)]:
        f=bytearray(32);f[:len(name)]=name.encode();f[11]=ord('C');f[16]=width;h+=f
    h+=b'\r'
    for key,lsadc in rows:h+=b' '+key.encode()+lsadc.encode()
    return bytes(h)+b'\x1a'


def test_dbf_exact_strings_and_leading_zero():
    rows,info=parse_dbf(dbf([('7200100001','00'),('7200100002','41')]))
    assert rows[0]['LSADC']=='00' and rows[0]['LSADC_RAW_HEX']=='3030'
    assert rows[0]['GEOID']=='7200100001' and info['dbf_record_count']==2


@pytest.mark.parametrize('mutation,error',[
    (lambda b:b[:98],'TRUNCATED'),
    (lambda b:b[:97]+b'*'+b[98:],'DELETED'),
    (lambda b:bytes([0])+b[1:],'UNSUPPORTED'),
])
def test_bad_dbf(mutation,error):
    with pytest.raises(ValueError,match=error):parse_dbf(mutation(dbf([('7200100001','20')])))


def test_dbf_duplicate_key_rejected():
    with pytest.raises(ValueError,match='DUPLICATE_STABLE_ID'):
        parse_dbf(dbf([('7200100001','20'),('7200100001','41')]))


def test_hash_gate(tmp_path):
    p=tmp_path/'blob';p.write_bytes(b'abc')
    with pytest.raises(ValueError,match='SHA256_MISMATCH'):checked_bytes(p,'0'*64)
    with pytest.raises(ValueError,match='BYTE_COUNT'):checked_bytes(p,digest(b'abc'),2)
    assert checked_bytes(p,digest(b'abc'),3)==b'abc'


def test_idempotent_receipt_and_collision(tmp_path):
    p=tmp_path/'r.json';write_new(p,{'a':1});write_new(p,{'a':1})
    with pytest.raises(ValueError,match='ALREADY_EXISTS_DIFFERENT'):write_new(p,{'a':2})


def test_no_empty_fc_pass(tmp_path):
    p=tmp_path/'e.geojson';p.write_text('{"type":"FeatureCollection","features":[]}')
    with pytest.raises(ValueError,match='EMPTY_FEATURE'):load_geojson(p,digest(p.read_bytes()),'GEOID')
    pytest.importorskip("shapely")
    pytest.importorskip("pyproj")
    from tools.gis_evidence.simplification import compare_layers
    with pytest.raises(ValueError,match='EMPTY_COMPARISON'):compare_layers({}, {},'EPSG:4326','EPSG:6566')


def test_missing_sources_block_without_acquisition():
    r=preflight({'layer_id':'tracts'})
    assert r['state']=='BLOCKED' and not r['source_acquisition_performed']
    assert r['source_loaded'] is False


def test_tile_math():
    assert tile_xy(0,0,1)==(1,1)
    assert all(0<=v<1024 for v in tile_xy(-66.4,18.22,10))


def test_summary_does_not_promote():
    r=measured_summary([{'viewport_id':'a','mode':'mvt','http_data_body_bytes':12,'measurement':{'time_to_data_idle_ms':1,'peak_main_thread_js_heap_bytes':None}}])
    assert r['automatic_publication'] is False and r['mvt_canonical'] is False


@pytest.mark.parametrize("url",["https://www2.census.gov/x.zip","http://example.org/tiles/0/0/0","file:///tmp/data.zip"])
def test_benchmark_rejects_nonloopback_or_nonhttp(url):
    from tools.gis_evidence.delivery_benchmark import request
    with pytest.raises(ValueError,match="LOCAL_FROZEN_DELIVERY_ONLY"):
        request(url)


def test_benchmark_disallows_redirect_escape():
    from tools.gis_evidence.delivery_benchmark import NoRedirect
    assert NoRedirect().redirect_request(None,None,302,"Found",{},"https://www2.census.gov/") is None
