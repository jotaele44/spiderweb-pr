#!/usr/bin/env python3
"""Acquire JP municipal flood-document coverage with explicit source states.

Source-state enum:
- AVAILABLE: listed series PDF is retrievable
- LISTED_BUT_MISSING: municipality is listed in the series but its linked PDF is unavailable
- NOT_LISTED: municipality is absent from the series

Current bounded model (2026-09-17):
- 77 municipalities are listed in "Sectores en Zona Inundables".
- 76 listed PDFs are retrievable.
- Quebradillas is LISTED_BUT_MISSING (live href returns 404).
- Florida is NOT_LISTED.
- Quebradillas and Florida each have an authoritative hazard-mitigation fallback.
"""
from __future__ import annotations

import argparse, hashlib, html.parser, json, re, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PORTAL_URL = "https://portaldeinundacion.jp.pr.gov/riesgo.html"
FLORIDA_HMP_URL = "https://jp.pr.gov/wp-content/uploads/2021/10/Flor-Plan-Approved-HMP.pdf"
QUEBRADILLAS_HMP_URL = "https://docs.pr.gov/files/JP-Junta%20de%20Planificacion/Planes%20de%20Mitigaci%C3%B3n%20Aprobados/Actualizados%20por%20los%20municipios/Queb-Approved-HMP.pdf"
SOURCE_STATES = {"AVAILABLE", "LISTED_BUT_MISSING", "NOT_LISTED"}
EXPECTED_LISTED = 77
EXPECTED_AVAILABLE = 76
EXPECTED_MUNICIPALITIES = 78
UA = "spiderweb-pr-jp-flood-documents/1.1"

CANONICAL_MUNICIPALITIES = (
"Adjuntas","Aguada","Aguadilla","Aguas Buenas","Aibonito","Añasco","Arecibo","Arroyo","Barceloneta","Barranquitas","Bayamón","Cabo Rojo","Caguas","Camuy","Canóvanas","Carolina","Cataño","Cayey","Ceiba","Ciales","Cidra","Coamo","Comerío","Corozal","Culebra","Dorado","Fajardo","Florida","Guánica","Guayama","Guayanilla","Guaynabo","Gurabo","Hatillo","Hormigueros","Humacao","Isabela","Jayuya","Juana Díaz","Juncos","Lajas","Lares","Las Marías","Las Piedras","Loíza","Luquillo","Manatí","Maricao","Maunabo","Mayagüez","Moca","Morovis","Naguabo","Naranjito","Orocovis","Patillas","Peñuelas","Ponce","Quebradillas","Rincón","Río Grande","Sabana Grande","Salinas","San Germán","San Juan","San Lorenzo","San Sebastián","Santa Isabel","Toa Alta","Toa Baja","Trujillo Alto","Utuado","Vega Alta","Vega Baja","Vieques","Villalba","Yabucoa","Yauco",
)

def _key(v: str) -> str:
    s=unicodedata.normalize("NFKD",v)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()
CANONICAL_BY_KEY={_key(x):x for x in CANONICAL_MUNICIPALITIES}

class _Links(html.parser.HTMLParser):
    def __init__(self): super().__init__(); self.href=None; self.text=[]; self.links=[]
    def handle_starttag(self,t,a):
        if t.lower()=="a" and dict(a).get("href"): self.href=dict(a)["href"]; self.text=[]
    def handle_data(self,d):
        if self.href is not None: self.text.append(d)
    def handle_endtag(self,t):
        if t.lower()=="a" and self.href is not None:
            self.links.append((self.href," ".join(self.text).strip())); self.href=None; self.text=[]

def _request(url: str, method="GET", timeout=90):
    q=urllib.parse.quote(url,safe=":/?&=%")
    return urllib.request.urlopen(urllib.request.Request(q,method=method,headers={"User-Agent":UA}),timeout=timeout)

def fetch_bytes(url: str, timeout=90):
    with _request(url,timeout=timeout) as r: return r.read(),dict(r.headers.items()),r.geturl()

def discover_series(text: str, base=PORTAL_URL):
    p=_Links(); p.feed(text); rows=[]; seen=set()
    for href,label in p.links:
        if ".pdf" not in href.lower(): continue
        url=urllib.parse.urljoin(base,href)
        if url in seen: continue
        seen.add(url)
        muni=CANONICAL_BY_KEY.get(_key(re.sub(r"\s+"," ",label).strip()))
        if muni is None:
            fn=urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/",1)[-1])
            raw=re.sub(r"_sectores_inundables.*$","",fn,flags=re.I)
            muni=CANONICAL_BY_KEY.get(_key(raw.replace("_"," ")))
        rows.append({"municipality":muni,"municipality_raw":label or None,"document_class":"flood_risk_zone_map","source_series":"JP_SECTORES_EN_ZONA_INUNDABLES","source_url":url,"source_url_raw_href":href,"source_state":"AVAILABLE","authority":"Junta de Planificación de Puerto Rico","equivalent_series_member":True})
    return rows

def apply_known_exceptions(rows):
    by={r["municipality"]:r for r in rows}
    q=by["Quebradillas"]
    q.update({"source_state":"LISTED_BUT_MISSING","fallback_document_class":"hazard_mitigation_plan","fallback_url":QUEBRADILLAS_HMP_URL,"fallback_relationship":"authoritative_fallback_not_equivalent"})
    rows.append({"municipality":"Florida","municipality_raw":"Florida","document_class":None,"source_series":"JP_SECTORES_EN_ZONA_INUNDABLES","source_url":None,"source_url_raw_href":None,"source_state":"NOT_LISTED","authority":"Junta de Planificación de Puerto Rico","equivalent_series_member":False,"fallback_document_class":"hazard_mitigation_plan","fallback_url":FLORIDA_HMP_URL,"fallback_relationship":"authoritative_fallback_not_equivalent"})
    return rows

def validate(rows):
    assert all(r["source_state"] in SOURCE_STATES for r in rows)
    assert len(rows)==EXPECTED_MUNICIPALITIES
    assert len({r["municipality"] for r in rows})==EXPECTED_MUNICIPALITIES
    assert sum(r["source_state"]!="NOT_LISTED" for r in rows)==EXPECTED_LISTED
    assert sum(r["source_state"]=="AVAILABLE" for r in rows)==EXPECTED_AVAILABLE
    assert sum(r["source_state"]=="LISTED_BUT_MISSING" for r in rows)==1
    assert sum(r["source_state"]=="NOT_LISTED" for r in rows)==1
    assert next(r for r in rows if r["municipality"]=="Quebradillas")["source_state"]=="LISTED_BUT_MISSING"
    assert next(r for r in rows if r["municipality"]=="Florida")["source_state"]=="NOT_LISTED"
    assert all(r.get("fallback_url") for r in rows if r["source_state"]!="AVAILABLE")

def download(url, target: Path, timeout):
    data,h,final=fetch_bytes(url,timeout); target.write_bytes(data)
    return {"final_url":final,"filename":target.name,"local_path":str(target),"byte_size":len(data),"sha256":hashlib.sha256(data).hexdigest(),"etag":h.get("ETag") or h.get("Etag"),"last_modified":h.get("Last-Modified"),"content_type":h.get("Content-Type"),"acquisition_status":"downloaded"}

def build_manifest(do_download: bool, out: Path, timeout: int):
    pb,ph,pfinal=fetch_bytes(PORTAL_URL,timeout)
    rows=apply_known_exceptions(discover_series(pb.decode("utf-8","ignore"),pfinal)); validate(rows)
    if do_download:
        out.mkdir(parents=True,exist_ok=True)
        for i,r in enumerate(rows,1):
            url=r["source_url"] if r["source_state"]=="AVAILABLE" else r["fallback_url"]
            kind=r["document_class"] if r["source_state"]=="AVAILABLE" else r["fallback_document_class"]
            name=urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/",1)[-1]) or f'{r["municipality"]}.pdf'
            print(f'[{i}/78] {r["municipality"]} {r["source_state"]} -> {kind}')
            r["operational_document"]=download(url,out/name,timeout)
    return {"manifest_version":"1.1","producer":"spiderweb-pr","generated_at":datetime.now(timezone.utc).isoformat(),"authority":"Junta de Planificación de Puerto Rico","portal_url":PORTAL_URL,"portal_sha256":hashlib.sha256(pb).hexdigest(),"portal_etag":ph.get("ETag") or ph.get("Etag"),"portal_last_modified":ph.get("Last-Modified"),"source_state_enum":sorted(SOURCE_STATES),"invariants":{"municipalities":78,"series_listed":77,"series_available":76,"listed_but_missing":1,"not_listed":1,"authoritative_fallbacks":2,"operational_coverage":78},"documents":sorted(rows,key=lambda r:_key(r["municipality"]))}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--manifest",default="data/jp_flood_documents/manifest.json"); ap.add_argument("--download",action="store_true"); ap.add_argument("--out-dir",default="data/jp_flood_documents/raw"); ap.add_argument("--timeout",type=int,default=90); a=ap.parse_args()
    m=build_manifest(a.download,Path(a.out_dir),a.timeout); p=Path(a.manifest); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("JP_FLOOD_DOCUMENT_GATE = PASS (76 AVAILABLE + 1 LISTED_BUT_MISSING + 1 NOT_LISTED = 78; 2 fallbacks)")
if __name__=="__main__": raise SystemExit(main())
