#!/usr/bin/env python3
"""Freeze NOAA NSDE CUSP index manifestations over the Puerto Rico discovery bbox.

The endpoint contract comes from frozen NSDE app.js:
  cuspidx -> vector-tile index
  feature.properties.name -> /downloads/<name>.zip

This script freezes metadata and only the vector tiles intersecting a bounded PR
bbox. NSDE serves these PBF tiles gzip-compressed, so raw response bytes are
preserved and a decompressed copy is used only for vector-tile decoding. It
discovers exact CUSP download names but never promotes regional-package or
shoreline coverage to canonical insular identity.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

META = "https://nsde.ngs.noaa.gov/cusp/cuspidx/metadata.json"
TILE = "https://nsde.ngs.noaa.gov/cusp/cuspidx/{z}/{x}/{y}.pbf"
DOWNLOAD = "https://nsde.ngs.noaa.gov/downloads/{name}.zip"
BBOX = (-68.1, 17.7, -64.9, 18.7)
UA = "spiderweb-pr-cusp-index/1.1 (+https://github.com/jotaele44/spiderweb-pr)"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(b: bytes):
    return hashlib.sha256(b).hexdigest()


def get(url: str, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def lon2x(lon, z):
    return int((lon + 180.0) / 360.0 * (1 << z))


def lat2y(lat, z):
    lat_rad = math.radians(lat)
    return int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * (1 << z))


def tiles_for_bbox(z):
    west, south, east, north = BBOX
    x0, x1 = sorted((lon2x(west, z), lon2x(east, z)))
    y0, y1 = sorted((lat2y(north, z), lat2y(south, z)))
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def decode_payload(data: bytes) -> tuple[bytes, str]:
    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data), "GZIP"
    return data, "IDENTITY"


def main() -> int:
    import argparse
    import mapbox_vector_tile

    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/noaa_cusp_index")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    meta_b, meta_h = get(META)
    (out / "metadata.json").write_bytes(meta_b)
    meta = json.loads(meta_b.decode("utf-8"))
    minzoom = int(meta.get("minzoom", 0))
    maxzoom = int(meta.get("maxzoom", minzoom))
    z = maxzoom
    while z > minzoom and len(tiles_for_bbox(z)) > 64:
        z -= 1

    tile_records = []
    names = set()
    layer_counts = {}
    for x, y in tiles_for_bbox(z):
        url = TILE.format(z=z, x=x, y=y)
        try:
            data, headers = get(url, timeout=60)
        except Exception as exc:
            tile_records.append({"z":z,"x":x,"y":y,"url":url,"state":"BLOCKED_TRANSPORT","error":repr(exc)})
            continue
        path = out / "tiles" / str(z) / str(x) / f"{y}.pbf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        try:
            decode_bytes, encoding = decode_payload(data)
            decoded = mapbox_vector_tile.decode(decode_bytes)
            feature_count = 0
            tile_names = set()
            for layer_name, layer in decoded.items():
                feats = layer.get("features", []) if isinstance(layer, dict) else []
                layer_counts[layer_name] = layer_counts.get(layer_name, 0) + len(feats)
                feature_count += len(feats)
                for feat in feats:
                    props = feat.get("properties") or {}
                    name = props.get("name")
                    if name not in (None, ""):
                        tile_names.add(str(name))
                        names.add(str(name))
            tile_records.append({"z":z,"x":x,"y":y,"url":url,"state":"PASS_TILE_FROZEN","path":str(path),"size_bytes":len(data),"sha256":sha(data),"transport_encoding":encoding,"decoded_size_bytes":len(decode_bytes),"content_type":headers.get("Content-Type"),"feature_count":feature_count,"names":sorted(tile_names)})
        except Exception as exc:
            tile_records.append({"z":z,"x":x,"y":y,"url":url,"state":"BLOCKED_DECODE","path":str(path),"size_bytes":len(data),"sha256":sha(data),"error":repr(exc)})

    downloads = []
    for name in sorted(names):
        url = DOWNLOAD.format(name=name)
        rec = {"name":name,"url":url,"retrieval_utc":now()}
        try:
            data, headers = get(url, timeout=120)
            path = out / "downloads" / f"{name}.zip"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            rec.update({"path":str(path),"size_bytes":len(data),"sha256":sha(data),"content_type":headers.get("Content-Type")})
            if not zipfile.is_zipfile(path):
                rec["state"] = "BLOCKED_NOT_ZIP"
                rec["archive_member_count"] = 0
            else:
                members=[]
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        if info.is_dir(): continue
                        payload=zf.read(info)
                        members.append({"path":info.filename,"compressed_size":info.compress_size,"uncompressed_size":info.file_size,"sha256":sha(payload)})
                rec["state"]="PASS_ARCHIVE_FROZEN"
                rec["archive_member_count"]=len(members)
                rec["archive_members"]=members
        except Exception as exc:
            rec.update({"state":"BLOCKED_TRANSPORT","error":repr(exc),"archive_member_count":0})
        downloads.append(rec)

    manifest={
        "schema_version":"1.1",
        "generated_utc":now(),
        "source_family":"NOAA_NSDE_CUSP",
        "discovery_bbox":BBOX,
        "metadata":{"url":META,"path":str(out/"metadata.json"),"size_bytes":len(meta_b),"sha256":sha(meta_b),"content_type":meta_h.get("Content-Type"),"minzoom":minzoom,"maxzoom":maxzoom,"selected_zoom":z},
        "tile_count_expected":len(tiles_for_bbox(z)),
        "tiles":tile_records,
        "layer_feature_counts":layer_counts,
        "discovered_download_names":sorted(names),
        "downloads":downloads,
        "rules":{"index_scope":"discovery only","download_name":"must come from feature.properties.name in frozen CUSP index tile","raw_tile":"raw compressed response is evidence; decompression is a derived decode step","identity":"no CUSP index/package/shoreline relation independently establishes canonical insular identity"},
        "certification":{"CUSP_INDEX":"OPEN","CUSP_DOWNLOAD_MANIFESTATIONS":"OPEN","GEOMETRIC_CURRENT":"OPEN","CURRENT_PR_ARCHIPELAGO":"OPEN"}
    }
    manifest["tile_pass_count"]=sum(x.get("state")=="PASS_TILE_FROZEN" for x in tile_records)
    manifest["download_pass_count"]=sum(x.get("state")=="PASS_ARCHIVE_FROZEN" for x in downloads)
    manifest["tile_arithmetic_closed"]=manifest["tile_pass_count"] + sum(x.get("state")!="PASS_TILE_FROZEN" for x in tile_records)==manifest["tile_count_expected"]
    manifest["tile_zero_failure_gate"]=manifest["tile_pass_count"]==manifest["tile_count_expected"]
    manifest["download_arithmetic_closed"]=manifest["download_pass_count"] + sum(x.get("state")!="PASS_ARCHIVE_FROZEN" for x in downloads)==len(downloads)
    if manifest["tile_zero_failure_gate"]:
        manifest["certification"]["CUSP_INDEX"]="PASS_BOUNDED_PR_BBOX"
    if manifest["download_arithmetic_closed"] and downloads:
        manifest["certification"]["CUSP_DOWNLOAD_MANIFESTATIONS"]="PASS_SOURCE_MANIFESTATION_ARITHMETIC"
    mp=out/"cusp_pr_manifest.json"
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"manifest":str(mp),"sha256":sha(mp.read_bytes()),"selected_zoom":z,"tile_count":manifest["tile_count_expected"],"tile_pass_count":manifest["tile_pass_count"],"tile_zero_failure_gate":manifest["tile_zero_failure_gate"],"names":sorted(names),"download_pass_count":manifest["download_pass_count"]},indent=2))
    return 0 if manifest["tile_zero_failure_gate"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
