"""Build and verify deterministic federation offline geospatial packages."""
from __future__ import annotations
import hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from typing import Iterable
from .spatial_core import canonical_json_sha256
PACKAGE_VERSION="fedgeopack/1.0"

def _sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
 return h.hexdigest()

def _safe_name(prefix:str,path:Path)->str:
 name=PurePosixPath(prefix)/path.name
 if name.is_absolute() or ".." in name.parts:raise ValueError("unsafe package member")
 return str(name)

def build_package(output:Path|str,*,producer_repo:str,layers:Iterable[Path|str]=(),rasters:Iterable[Path|str]=(),styles:Iterable[Path|str]=(),crs:str="OGC:CRS84",provenance:list[dict]|None=None,investigation:dict|None=None)->dict:
 out=Path(output); members=[]
 for prefix,items in (("layers",layers),("rasters",rasters),("styles",styles)):
  for raw in items:
   p=Path(raw)
   if not p.is_file():raise FileNotFoundError(p)
   members.append((p,_safe_name(prefix,p),_sha(p)))
 hashes={arc:digest for _,arc,digest in members}
 layer_rows=[{"layer_id":Path(arc).stem,"path":arc,"format":Path(arc).suffix.lstrip(".").lower(),"sha256":digest} for _,arc,digest in members if arc.startswith("layers/")]
 raster_rows=[{"layer_id":Path(arc).stem,"path":arc,"format":"cog" if Path(arc).suffix.lower() in {".tif",".tiff"} else Path(arc).suffix.lstrip(".").lower(),"sha256":digest} for _,arc,digest in members if arc.startswith("rasters/")]
 core={"package_version":PACKAGE_VERSION,"producer_repo":producer_repo,"crs":crs,"layers":layer_rows,"rasters":raster_rows,"styles":[{"path":arc,"sha256":d} for _,arc,d in members if arc.startswith("styles/")],"hashes":hashes,"provenance":provenance or [],"investigation":investigation,"access_class":"PUBLIC"}
 core["package_id"]=canonical_json_sha256(core)[:32]; core["created_at"]=datetime.now(timezone.utc).isoformat()
 out.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
  for p,arc,_ in sorted(members,key=lambda x:x[1]):z.write(p,arc)
  z.writestr("manifest.json",json.dumps(core,sort_keys=True,separators=(",",":"),ensure_ascii=False))
 return core

def verify_package(path:Path|str)->dict:
 with zipfile.ZipFile(path,"r") as z:
  names=z.namelist()
  for name in names:
   p=PurePosixPath(name)
   if p.is_absolute() or ".." in p.parts:raise ValueError(f"unsafe package member: {name}")
  manifest=json.loads(z.read("manifest.json"))
  if manifest.get("package_version")!=PACKAGE_VERSION:raise ValueError("unsupported package version")
  for name,expected in manifest.get("hashes",{}).items():
   actual=hashlib.sha256(z.read(name)).hexdigest()
   if actual!=expected:raise ValueError(f"hash mismatch: {name}")
 return manifest
