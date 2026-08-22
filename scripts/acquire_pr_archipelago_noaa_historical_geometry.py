#!/usr/bin/env python3
"""Freeze exact NSDE archives for the bounded NOAA historical PR source set.

B-only lane. The eight project codes come from the independently bounded NOAA
historical metadata denominator. Exact NSDE download construction is reused from
the frozen client contract, but none of these bytes may fill or certify A.
"""
from __future__ import annotations
import hashlib, json, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE="https://nsde.ngs.noaa.gov/downloads/"
UA="spiderweb-pr-noaa-historical-geometry/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
PROJECTS=["PH6106","PH6403","PH6403DZ","PH6708","PH6903","PR1901A","PR1901B","PR1926A"]

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def sha(b): return hashlib.sha256(b).hexdigest()
def get(url,timeout=120):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read(),dict(r.headers.items())

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='evidence/pr_archipelago/historical_snapshots/noaa_geometry'); args=ap.parse_args()
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for code in PROJECTS:
        url=BASE+code+'.zip'; rec={'project_code':code,'url':url,'retrieval_utc':now()}
        try:
            data,h=get(url); p=out/(code+'.zip'); p.write_bytes(data)
            rec.update({'path':str(p),'size_bytes':len(data),'sha256':sha(data),'content_type':h.get('Content-Type')})
            if not zipfile.is_zipfile(p):
                rec.update({'state':'BLOCKED_NOT_ZIP','archive_member_count':0})
            else:
                members=[]
                with zipfile.ZipFile(p) as z:
                    for info in z.infolist():
                        if info.is_dir(): continue
                        payload=z.read(info); members.append({'path':info.filename,'compressed_size':info.compress_size,'uncompressed_size':info.file_size,'sha256':sha(payload)})
                rec.update({'state':'PASS_ARCHIVE_FROZEN','archive_member_count':len(members),'archive_members':members})
        except Exception as exc:
            rec.update({'state':'BLOCKED_TRANSPORT','archive_member_count':0,'error':repr(exc)})
        rows.append(rec)
    passn=sum(r['state']=='PASS_ARCHIVE_FROZEN' for r in rows)
    m={'schema_version':'1.0','generated_utc':now(),'scope':'B-only NOAA historical Puerto Rico shoreline project archives','expected_project_count':len(PROJECTS),'projects':rows,'pass_archive_count':passn,'blocked_count':len(PROJECTS)-passn,'arithmetic_closed':len(rows)==len(PROJECTS),'rules':{'current_contamination':'forbidden; historical geometry never fills A','identity':'historical archive/project membership does not establish current canonical identity'},'certification':{'NOAA_HISTORICAL_GEOMETRY_ARCHIVES':'PASS_SOURCE_MANIFESTATION_ARITHMETIC' if len(rows)==len(PROJECTS) else 'FAIL','HISTORICAL_ARCHIPELAGO_EXHAUSTION':'OPEN','CURRENT_PR_ARCHIPELAGO':'UNCHANGED_OPEN'}}
    mp=out/'noaa_historical_geometry_manifest.json'; mp.write_text(json.dumps(m,ensure_ascii=False,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({'manifest':str(mp),'sha256':sha(mp.read_bytes()),'expected':len(PROJECTS),'pass_archive_count':passn,'blocked_count':len(PROJECTS)-passn,'arithmetic_closed':m['arithmetic_closed']},indent=2))
    return 0 if m['arithmetic_closed'] else 2
if __name__=='__main__': raise SystemExit(main())
