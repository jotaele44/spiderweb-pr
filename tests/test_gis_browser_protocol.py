"""Real Chromium, explicitly stubbed MapLibre protocol; NOT renderer certification.

Exercises the production embedded JS event/capture/cleanup path without needing
Martin or a MapLibre distribution. A separate real-engine smoke run is required.
"""
import shutil

import pytest

from tools.gis_evidence.delivery_benchmark import HTML
from tools.gis_evidence.viewport_parity import compare_rendered_trials

STUB = r'''
window.maplibregl={version:'TEST_PROTOCOL_STUB_NOT_MAPLIBRE',Map:class {
 constructor(options){this.opts=options;this.events={};this.source=null;this.i=-1;this.center=options.center;this.zoom=options.zoom;this.canvas=document.createElement('canvas');this.canvas.width=innerWidth;this.canvas.height=innerHeight;document.querySelector('#map').appendChild(this.canvas);setTimeout(()=>this.emit('load'),0)}
 on(k,fn){(this.events[k]??=[]).push(fn);return this}
 off(k,fn){this.events[k]=(this.events[k]||[]).filter(f=>f!==fn);return this}
 emit(k,e={}){for(const fn of [...(this.events[k]||[])])fn(e)}
 addSource(k,s){this.source=s;this.mode=s.type==='vector'?'mvt':'geojson'}
 getSource(){return this.source}
 isSourceLoaded(){return true}
 areTilesLoaded(){return true}
 isMoving(){return !!this.moving}
 addLayer(){setTimeout(()=>this.emit('idle'),0)}
 getCenter(){return {lng:this.center[0],lat:this.center[1]}}
 getZoom(){return this.zoom}
 getPitch(){return 0}
 getBearing(){return 0}
 getCanvas(){return this.canvas}
 queryRenderedFeatures(){const step=this.i<0?'initial':'pan:'+this.i;return window.FIXTURE[this.mode][step].map(v=>({properties:{GEOID:v}}))}
 easeTo(o){this.moving=true;this.i++;this.center=[...o.center];this.zoom=o.zoom;if(window.FIXTURE.cameraOffset&&this.mode==='mvt')this.center[0]+=0.001;setTimeout(()=>{this.moving=false;this.emit(window.FIXTURE.panError?'error':'idle',{error:'synthetic protocol error'})},0)}
 remove(){window.removed=(window.removed||0)+1;this.canvas.remove()}
}};
'''




@pytest.fixture(scope="module")
def chromium():
    api = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium")
    if binary is None:
        pytest.skip("Protocol test requires Chromium; real engine smoke remains separate")
    with api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary,headless=True,
                                   args=["--disable-dev-shm-usage"])
        yield browser
        browser.close()


@pytest.fixture
def probe(chromium):
    context = chromium.new_context(viewport={"width":1280,"height":800})
    page = context.new_page()
    page.route("**/*", lambda route: route.abort())
    # In-memory protocol test. No local server, network transport, real
    # MapLibre renderer or Martin process is implied by a passing result.
    document = HTML.replace('<script src="/maplibre.js"></script>',
                            '<script>'+STUB+'</script>')
    page.set_content(document)
    yield page
    context.close()


def fixture():
    return {"geojson":{"initial":["a","a","b"],"pan:0":["b"]},
            "mvt":{"initial":["a","b","b"],"pan:0":["b","b"]}}


def measure(page, payload, mode):
    page.evaluate("v=>{window.FIXTURE=v}",payload)
    return page.evaluate("c=>window.measure(c)",{
        "mode":mode,"center":[-66.4,18.22],"zoom":9,"source_layer":"synthetic",
        "id_field":"GEOID","pan_path":[[-66.25,18.28]],
        "expect_nonempty":True,"timeout_ms":2000})


def compare(measurements):
    trials=[{"viewport_id":"v","repetition":0,"mode":mode,"measurement":m}
            for mode,m in measurements.items()]
    spec={"repetitions":1,"viewports":[{"id":"v","center":[-66.4,18.22],
        "zoom":9,"pan_path":[[-66.25,18.28]],"expect_nonempty":True}]}
    return compare_rendered_trials(trials,spec,{"a","b","c"})


def test_protocol_capture_initial_and_pan_in_chromium(probe):
    results={mode:measure(probe,fixture(),mode) for mode in ("geojson","mvt")}
    r=compare(results)
    assert r["state"]=="PASS_RENDERED_ID_PARITY"
    assert r["paired_checkpoint_count"]==2
    assert results["geojson"]["viewport_snapshots"][0]["rendered_fragment_count"]==3
    assert results["geojson"]["viewport_snapshots"][0]["visible_ids"]==["a","b"]
    assert probe.evaluate("window.removed")==2


def test_protocol_detects_pan_only_mismatch(probe):
    payload=fixture();payload["mvt"]["pan:0"]=["c"]
    r=compare({mode:measure(probe,payload,mode) for mode in ("geojson","mvt")})
    assert r["records"][0]["state"]=="PASS"
    assert r["records"][1]["sets"]["ids"]["symmetric_difference"]==["b","c"]
    assert r["state"]=="FAIL_RENDERED_ID_PARITY"


def test_protocol_detects_camera_divergence(probe):
    payload=fixture();payload["cameraOffset"]=True
    r=compare({mode:measure(probe,payload,mode) for mode in ("geojson","mvt")})
    assert "mvt:CAMERA_TARGET_MISMATCH" in r["records"][1]["errors"]


def test_protocol_invalid_rendered_id_is_not_filtered_out(probe):
    payload=fixture();payload["mvt"]["initial"]=["a",None]
    with pytest.raises(Exception,match="invalid stable ID"):
        measure(probe,payload,"mvt")
    assert probe.evaluate("window.removed")==1


def test_protocol_empty_late_view_is_not_a_fast_winner(probe):
    payload=fixture();payload["mvt"]["pan:0"]=[]
    with pytest.raises(Exception,match="expected visible data"):
        measure(probe,payload,"mvt")
    assert probe.evaluate("window.removed")==1


def test_protocol_error_cleans_up_map(probe):
    payload=fixture();payload["panError"]=True
    with pytest.raises(Exception,match="synthetic protocol error"):
        measure(probe,payload,"mvt")
    assert probe.evaluate("window.removed")==1
