"""Frozen-input GeoJSON/Martin A/B runner. Never downloads source data.

Generalizes the existing municipios canary's tile-grid ID reconstruction and
GeoJSON rollback pattern. Requires local, hash-bound MapLibre JS and Martin.
Browser measurements are cold-browser/warm-server, not Internet performance.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import socket
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .core import checked_bytes, canonical_json, digest, load_geojson, set_receipt, write_new

HTML = r'''<!doctype html><meta charset="utf-8"><style>
html,body,#map {margin:0;width:100%;height:100%;overflow:hidden}
.maplibregl-canvas {position:absolute;left:0;top:0}
</style><div id="map"></div><script src="/maplibre.js"></script><script>
window.measure = async function(config) {
  const map = new maplibregl.Map({container:'map',style:{version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#ffffff'}}]},center:config.center,zoom:config.zoom,fadeDuration:0,attributionControl:false,collectResourceTiming:true});
  const errors=[];map.on('error',e=>errors.push(String(e.error || e)));
  await new Promise((resolve,reject)=>{map.once('load',resolve);setTimeout(()=>reject(new Error('map shell timeout')),config.timeout_ms)});
  performance.clearResourceTimings();
  const start=performance.now();
  let maximumMainHeap=null,stopped=false;
  const heapTimer=setInterval(()=>{const value=performance.memory?.usedJSHeapSize;if(Number.isFinite(value))maximumMainHeap=Math.max(maximumMainHeap||0,value);},25);
  try {
    const complete=new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('data/idle timeout')),config.timeout_ms);
      map.once('idle',()=>{clearTimeout(timer);resolve()});
    });
    if(config.mode==='geojson') map.addSource('data',{type:'geojson',data:'/source.geojson',promoteId:config.id_field});
    else map.addSource('data',{type:'vector',url:'/tilejson',promoteId:config.id_field});
    const sourceLayer=config.mode==='mvt'?{'source-layer':config.source_layer}:{};
    map.addLayer({id:'fill',type:'fill',source:'data',...sourceLayer,paint:{'fill-color':'#367eae','fill-opacity':0.45}});
    map.addLayer({id:'line',type:'line',source:'data',...sourceLayer,paint:{'line-color':'#17394d','line-width':0.7}});
    await complete;
    const idleMs=performance.now()-start;
    const visible=map.queryRenderedFeatures({layers:['fill']});
    const visibleIds=[...new Set(visible.map(f=>f.properties?.[config.id_field]).filter(v=>typeof v==='string'))].sort();
    if(config.expect_nonempty && !visibleIds.length)throw new Error('expected visible data but no stable IDs rendered');
    let previous=null;const intervals=[];
    function sample(t){if(stopped)return;if(previous!==null)intervals.push(t-previous);previous=t;requestAnimationFrame(sample)}
    requestAnimationFrame(sample);
    for(const stop of config.pan_path) {
      await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('pan timeout')),config.timeout_ms);map.once('idle',()=>{clearTimeout(timer);resolve()});map.easeTo({center:stop,zoom:config.zoom,duration:500,essential:true});});
    }
    stopped=true;
    const dataResources=performance.getEntriesByType('resource').filter(e=>e.name.includes('/source.geojson')||e.name.includes('/tilejson')||e.name.includes('/tiles/'));
    if(errors.length)throw new Error(errors.join(';'));
    return {maplibre_version:maplibregl.version,time_to_data_idle_ms:idleMs,visible_ids:visibleIds,raf_intervals_ms:intervals,peak_main_thread_js_heap_bytes:maximumMainHeap,heap_scope:'main-thread JS heap only; not total renderer/GPU/worker memory',resources:dataResources.map(e=>({name:e.name,transferSize:e.transferSize,encodedBodySize:e.encodedBodySize,decodedBodySize:e.decodedBodySize,duration:e.duration}))};
  } finally {stopped=true;clearInterval(heapTimer);map.remove();}
}
</script>'''


def preflight(spec: dict) -> dict:
    issues=[]; source=None;index=None
    if spec.get("source_crs") not in {"EPSG:4326","OGC:CRS84"} or spec.get("coordinate_order") != "longitude_latitude":
        issues.append("EXPLICIT_LONGITUDE_LATITUDE_INTERCHANGE_CRS_REQUIRED")
    if not re.fullmatch(r"[a-z][a-z0-9_]*",str(spec.get("layer_id",""))):
        issues.append("INVALID_LAYER_ID")
    if spec.get("data_kind") not in {"REAL_FROZEN","SYNTHETIC_TEST_ONLY"}:
        issues.append("DATA_KIND_REQUIRED")
    for key in ("source_path","source_sha256","stable_id_field","expected_feature_count","source_snapshot_id","manifestation_id","source_layer"):
        if spec.get(key) is None or spec.get(key)=="":issues.append("UNBOUND_"+key.upper())
    if not issues:
        try:
            source,index=load_geojson(Path(spec["source_path"]),spec["source_sha256"],spec["stable_id_field"])
            if len(index)!=spec["expected_feature_count"]:issues.append("SOURCE_COUNT_MISMATCH")
            from shapely.geometry import shape
            for key,feature in index.items():
                if feature.get("geometry") is None:
                    issues.append("NULL_GEOMETRY:"+key);continue
                g=shape(feature["geometry"])
                if g.is_empty or not g.is_valid or g.geom_type not in {"Polygon","MultiPolygon"}:issues.append("INVALID_POLYGON:"+key)
                if g.has_z:issues.append("UNDECLARED_Z_LOSS:"+key)
                if not g.is_empty and not (-180<=g.bounds[0]<=g.bounds[2]<=180 and -85<=g.bounds[1]<=g.bounds[3]<=85):issues.append("OUTSIDE_SUPPORTED_TILE_SCOPE:"+key)
        except (OSError,ValueError,TypeError) as exc:issues.append(str(exc))
    for key in ("martin_binary","maplibre_js"):
        runtime=spec.get(key,{})
        if not isinstance(runtime,dict):
            issues.append(key+":INVALID_RUNTIME_LOCK");continue
        if not isinstance(runtime.get("version"),str) or not runtime["version"]:
            issues.append(key+":RUNTIME_VERSION_REQUIRED")
        try:checked_bytes(Path(runtime.get("path","__MISSING__")),runtime.get("sha256",""))
        except (OSError,ValueError) as exc:issues.append(key+":"+str(exc))
    for package in ("playwright","mapbox_vector_tile"):
        if importlib.util.find_spec(package) is None:issues.append("MISSING_RUNTIME_DEPENDENCY:"+package)
    if type(spec.get("repetitions")) is not int or spec["repetitions"]<5:issues.append("AT_LEAST_FIVE_PAIRED_REPETITIONS_REQUIRED")
    if not spec.get("viewports"):issues.append("VIEWPORTS_REQUIRED")
    view_ids=set()
    for v in spec.get("viewports",[]):
        vid=v.get("id","")
        if not re.fullmatch(r"[a-zA-Z0-9_]+",str(vid)) or vid in view_ids:issues.append("INVALID_OR_DUPLICATE_VIEWPORT_ID")
        view_ids.add(vid)
        if not isinstance(v.get("zoom"),(int,float)) or not math.isfinite(v["zoom"]) or not 0<=v["zoom"]<=22:issues.append("INVALID_VIEWPORT_ZOOM")
        for pt in [v.get("center",[])]+v.get("pan_path",[]):
            if not isinstance(pt,list) or len(pt)!=2 or not all(isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) for x in pt):
                issues.append("INVALID_VIEWPORT_COORDINATE")
            elif not (-180<=pt[0]<=180 and -85<=pt[1]<=85):issues.append("OUT_OF_BOUNDS_VIEWPORT")
    if type(spec.get("identity_zoom")) is not int or not 0<=spec["identity_zoom"]<=14:issues.append("INVALID_IDENTITY_ZOOM")
    return {"state":"READY" if not issues else "BLOCKED","issues":issues,"source_loaded":source is not None,"source_feature_count":len(index) if index is not None else None,"source_acquisition_performed":False}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not permit a loopback endpoint to redirect the audit off-machine."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url: str) -> tuple[bytes,str,int]:
    parsed=urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1","localhost","::1"}:
        raise ValueError("LOCAL_FROZEN_DELIVERY_ONLY")
    req=urllib.request.Request(url,headers={"Accept-Encoding":"identity"})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:
        data=r.read(64*1024*1024+1)
        if len(data)>64*1024*1024:raise ValueError("HTTP_RESPONSE_BUDGET_EXCEEDED")
        if r.headers.get("Content-Encoding")=="gzip":data=gzip.decompress(data)
        return data,r.headers.get("Content-Type",""),r.status


def tile_xy(lon: float,lat: float,z: int) -> tuple[int,int]:
    n=1<<z
    return min(n-1,max(0,int((lon+180)/360*n))),min(n-1,max(0,int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)))


def reconstruct_ids(base: str,spec: dict,index: dict,out: Path) -> dict:
    import mapbox_vector_tile
    from shapely.geometry import shape
    z=spec["identity_zoom"];tiles=set()
    for feature in index.values():
        west,south,east,north=shape(feature["geometry"]).bounds
        x0,y1=tile_xy(west,south,z);x1,y0=tile_xy(east,north,z)
        for x in range(x0,x1+1):
            for y in range(y0,y1+1):tiles.add((z,x,y))
    if not tiles or len(tiles)>spec.get("max_identity_tiles",4096):raise ValueError("IDENTITY_TILE_BUDGET_EXCEEDED")
    ids=[];tile_receipts=[]
    for z,x,y in sorted(tiles):
        raw,ctype,status=request(f'{base}/{spec["layer_id"]}/{z}/{x}/{y}')
        name=f"{z}_{x}_{y}.pbf"; path=out/"identity_tiles"/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        found=[]
        if status==200 and raw:
            if not any(t in ctype.lower() for t in ("protobuf","vector-tile","octet-stream")):raise ValueError("MVT_CONTENT_TYPE_MISMATCH")
            decoded=mapbox_vector_tile.decode(raw)
            for feature in decoded.get(spec["source_layer"],{}).get("features",[]):
                key=feature.get("properties",{}).get(spec["stable_id_field"])
                if not isinstance(key,str) or not key.strip():raise ValueError("MVT_STABLE_ID_MISSING_OR_NONSTRING")
                found.append(key)
        elif status not in (200,204):raise ValueError(f"UNEXPECTED_TILE_STATUS:{status}")
        ids.extend(found)
        tile_receipts.append({"tile":[z,x,y],"sha256":digest(raw),"bytes":len(raw),"feature_fragments":len(found)})
    diff=set_receipt(set(index),set(ids))
    return {"state":"PASS" if not diff["counts"]["symmetric_difference"] else "FAIL","claim":"ID preservation within enumerated source-bbox tile coverage at stated zoom only; not geometric equality","zoom":z,"tiles":tile_receipts,"tile_count":len(tiles),"source_count":len(index),"decoded_fragment_count":len(ids),"decoded_unique_id_count":len(set(ids)),"repeated_tile_fragments":{k:v for k,v in Counter(ids).items() if v>1},"sets":diff}


@contextmanager
def martin_server(spec: dict,out: Path):
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    binary=Path(spec["martin_binary"]["path"]).resolve()
    checked_bytes(binary,spec["martin_binary"]["sha256"])
    version=subprocess.run([str(binary),"--version"],check=True,capture_output=True,text=True,timeout=15).stdout.strip()
    expected=spec["martin_binary"]["version"]
    if not re.search(r"(?<![0-9.])"+re.escape(expected)+r"(?![0-9.])",version):
        raise ValueError("MARTIN_VERSION_MISMATCH")
    write_new(out/"martin-runtime.json",{"sha256":spec["martin_binary"]["sha256"],"observed_version_output":version})
    config={"listen_addresses":f"127.0.0.1:{port}","geojson":{"sources":{spec["layer_id"]:str(Path(spec["source_path"]).resolve())}}}
    path=out/"martin-config.json";write_new(path,config)
    log=(out/"martin.log").open("wb")
    proc=subprocess.Popen([str(binary),"--config",str(path)],stdout=log,stderr=subprocess.STDOUT)
    try:
        base=f"http://127.0.0.1:{port}"
        ready=False
        for _ in range(100):
            if proc.poll() is not None:raise RuntimeError("MARTIN_EXITED_BEFORE_HEALTH")
            try:
                if request(base+"/health")[2]==200:ready=True;break
            except (OSError,urllib.error.URLError):pass
            time.sleep(.1)
        if not ready:raise RuntimeError("MARTIN_HEALTH_TIMEOUT")
        yield base
    finally:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close()


@contextmanager
def fixture_server(spec: dict,martin: str):
    js=checked_bytes(Path(spec["maplibre_js"]["path"]),spec["maplibre_js"]["sha256"])
    source=checked_bytes(Path(spec["source_path"]),spec["source_sha256"])
    zipped=gzip.compress(source,mtime=0)
    traffic=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            p=urlparse(self.path).path
            try:
                enc=None
                if p=="/":body,ctype=HTML.encode(),"text/html"
                elif p=="/maplibre.js":body,ctype=js,"application/javascript"
                elif p=="/source.geojson":body,ctype,enc=zipped,"application/geo+json","gzip"
                elif p=="/tilejson":
                    data,_,_=request(martin+"/"+spec["layer_id"])
                    obj=json.loads(data);obj["tiles"]=[f"http://127.0.0.1:{self.server.server_port}/tiles/{{z}}/{{x}}/{{y}}"]
                    body,ctype=canonical_json(obj),"application/json"
                elif re.fullmatch(r"/tiles/\d+/\d+/\d+",p):body,ctype,_=request(martin+"/"+spec["layer_id"]+p[6:])
                else:self.send_error(404);return
                self.send_response(200);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store")
                if enc:self.send_header("Content-Encoding",enc)
                self.end_headers();self.wfile.write(body)
                traffic.append({"path":p,"body_bytes":len(body)})
            except Exception as exc:
                traffic.append({"path":p,"error":str(exc)});self.send_error(502)
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f"http://127.0.0.1:{server.server_port}",traffic
    finally:server.shutdown();server.server_close();thread.join()


def measured_summary(trials: list[dict]) -> dict:
    groups={}
    for trial in trials:
        key=(trial["viewport_id"],trial["mode"])
        groups.setdefault(key,[]).append(trial)
    out=[]
    for (view,mode),rows in sorted(groups.items()):
        times=[r["measurement"]["time_to_data_idle_ms"] for r in rows]
        heap=[r["measurement"]["peak_main_thread_js_heap_bytes"] for r in rows if r["measurement"]["peak_main_thread_js_heap_bytes"] is not None]
        out.append({"viewport_id":view,"mode":mode,"trials":len(rows),"median_time_to_data_idle_ms":statistics.median(times),"median_http_data_body_bytes":statistics.median(r["http_data_body_bytes"] for r in rows),"median_peak_main_thread_js_heap_bytes":statistics.median(heap) if heap else None})
    return {"groups":out,"delivery_decision":"UNRESOLVED_PENDING_REVIEW_OF_MEASUREMENTS","automatic_publication":False,"geojson_rollback_required":True,"mvt_canonical":False}


def run(spec: dict,out: Path) -> dict:
    status=preflight(spec)
    if status["state"]!="READY":return {"layer_id":spec.get("layer_id"),"state":"BLOCKED","preflight":status,"delivery_decision":"UNRESOLVED_PENDING_BENCHMARK","mvt_canonical":False,"geojson_rollback_required":True}
    from playwright.sync_api import sync_playwright
    _,index=load_geojson(Path(spec["source_path"]),spec["source_sha256"],spec["stable_id_field"])
    trials=[]
    with martin_server(spec,out) as base:
        identity=reconstruct_ids(base,spec,index,out);write_new(out/"identity.json",identity)
        if identity["state"]!="PASS":return {"state":"FAIL","identity":identity,"delivery_decision":"KEEP_GEOJSON_IDENTITY_GATE_FAILED"}
        with fixture_server(spec,base) as (url,traffic),sync_playwright() as p:
            options={"headless":True,"args":["--enable-precise-memory-info"]}
            if spec.get("chromium_executable"):options["executable_path"]=spec["chromium_executable"]
            browser=p.chromium.launch(**options)
            browser_version=browser.version
            try:
                for view in spec["viewports"]:
                    for repetition in range(spec["repetitions"]):
                        modes=["geojson","mvt"] if repetition%2==0 else ["mvt","geojson"]
                        for mode in modes:
                            context=browser.new_context(viewport=spec.get("viewport_pixels",{"width":1280,"height":800}),device_scale_factor=1,service_workers="block")
                            try:
                                context.route("**/*",lambda route: route.continue_() if urlparse(route.request.url).hostname in {"127.0.0.1","localhost","::1"} else route.abort())
                                page=context.new_page();page.goto(url);page.wait_for_function("typeof window.measure==='function'")
                                traffic.clear()
                                cfg={"mode":mode,"center":view["center"],"zoom":view["zoom"],"source_layer":spec["source_layer"],"id_field":spec["stable_id_field"],"pan_path":view.get("pan_path",[]),"expect_nonempty":view.get("expect_nonempty",True),"timeout_ms":60000}
                                m=page.evaluate("c => window.measure(c)",cfg)
                                if m["maplibre_version"]!=spec["maplibre_js"]["version"]:raise ValueError("MAPLIBRE_VERSION_MISMATCH")
                                if any("error" in t for t in traffic):raise ValueError("HTTP_DATA_ERROR")
                                data_traffic=[t for t in traffic if t["path"]=="/source.geojson" or t["path"]=="/tilejson" or t["path"].startswith("/tiles/")]
                                row={"viewport_id":view["id"],"repetition":repetition,"mode":mode,"measurement":m,"http_data_requests":len(data_traffic),"http_data_body_bytes":sum(t["body_bytes"] for t in data_traffic),"traffic":data_traffic}
                                trials.append(row)
                                write_new(out/f'trial_{view["id"]}_{repetition}_{mode}.json',row)
                            finally:context.close()
            finally:browser.close()
    return {"state":"MEASURED_NOT_PUBLISHED","layer_id":spec["layer_id"],"data_kind":spec["data_kind"],"spec_sha256":digest(canonical_json(spec)),"source_sha256":spec["source_sha256"],"identity":identity,"trials":trials,"summary":measured_summary(trials),"environment":{"browser":browser_version,"python":platform.python_version(),"platform":platform.platform(),"cache_condition":"warm Martin after identity scan; fresh browser context per trial; no-store fixture responses","network":"local loopback; not representative of user Internet latency"},"completed_at_utc":datetime.now(timezone.utc).isoformat()}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--spec",type=Path,required=True);ap.add_argument("--out",type=Path,required=True);ap.add_argument("--preflight-only",action="store_true")
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    spec=json.loads(args.spec.read_text())
    try:
        result=preflight(spec) if args.preflight_only else run(spec,args.out)
    except Exception as exc:
        result={"state":"FAIL","error_type":type(exc).__name__,"error":str(exc),"delivery_decision":"UNRESOLVED_PENDING_BENCHMARK","mvt_canonical":False}
    write_new(args.out/"receipt.json",result)
    print(json.dumps({k:v for k,v in result.items() if k in {"state","layer_id","delivery_decision","issues"}},indent=2))
    return 0 if result["state"] in {"READY","MEASURED_NOT_PUBLISHED"} else 2


if __name__=="__main__":raise SystemExit(main())
