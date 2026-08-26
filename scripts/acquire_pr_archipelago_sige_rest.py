#!/usr/bin/env python3
"""Freeze official Puerto Rico SIGE ArcGIS REST manifestations.

This is an independent fallback after the WFS transport surface was exhausted
and timed out. ArcGIS REST source manifestations remain separate from WFS and
from canonical identity. Pagination is explicit and counts must close.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "spiderweb-pr-sige-rest/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
LAYERS = [
    {
        "id": "SIGE_COASTAL_SHORELINE",
        "url": "https://sige.pr.gov/server/rest/services/PuertoRico_Advisory/MapServer/15",
        "role": "GEOMETRY_SUPPORT_KNOWN_LIMITED",
    },
    {
        "id": "SIGE_MUNICIPALITY",
        "url": "https://sige.pr.gov/server/rest/services/PuertoRico_Advisory/MapServer/0",
        "role": "ADMINISTRATIVE_GEOMETRY_SUPPORT",
    },
    {
        "id": "SIGE_REFERENCIA_GEOGRAFICA",
        "url": "https://sige.pr.gov/server/rest/services/MIPR/ValorTuristico_v10_N/MapServer/7",
        "role": "LOCAL_NAMED_FEATURE_DISCOVERY",
    },
]


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def get(url: str, timeout=60) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def query_url(base: str, **params) -> str:
    return base.rstrip("/") + "/query?" + urllib.parse.urlencode(params)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/sige_rest")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "1.0", "generated_utc": now(), "layers": [], "certification": "OPEN"}

    for spec in LAYERS:
        layer_dir = out / spec["id"].lower()
        layer_dir.mkdir(parents=True, exist_ok=True)
        rec = {**spec, "state": "OPEN", "pages": []}
        try:
            metadata_url = spec["url"] + "?f=pjson"
            metadata, mh = get(metadata_url)
            (layer_dir / "metadata.json").write_bytes(metadata)
            meta_obj = json.loads(metadata.decode("utf-8"))
            rec["metadata"] = {
                "url": metadata_url,
                "sha256": sha(metadata),
                "size_bytes": len(metadata),
                "geometry_type": meta_obj.get("geometryType"),
                "max_record_count": meta_obj.get("maxRecordCount"),
                "supported_query_formats": meta_obj.get("supportedQueryFormats"),
            }

            count_url = query_url(spec["url"], where="1=1", returnCountOnly="true", f="json")
            count_bytes, _ = get(count_url)
            (layer_dir / "count.json").write_bytes(count_bytes)
            count_obj = json.loads(count_bytes.decode("utf-8"))
            expected = int(count_obj["count"])
            rec["count"] = {"url": count_url, "sha256": sha(count_bytes), "expected": expected}

            page_size = min(int(meta_obj.get("maxRecordCount") or 1000), 1000)
            merged = []
            offset = 0
            page_no = 0
            while offset < expected:
                url = query_url(
                    spec["url"], where="1=1", outFields="*", returnGeometry="true",
                    outSR="4326", f="geojson", resultOffset=str(offset),
                    resultRecordCount=str(page_size), orderByFields="OBJECTID ASC"
                )
                data, headers = get(url)
                pobj = json.loads(data.decode("utf-8"))
                if pobj.get("type") != "FeatureCollection" or not isinstance(pobj.get("features"), list):
                    raise RuntimeError(f"non-FeatureCollection page {page_no}")
                path = layer_dir / f"page_{page_no:04d}.geojson"
                path.write_bytes(data)
                feats = pobj["features"]
                rec["pages"].append({
                    "page": page_no, "offset": offset, "feature_count": len(feats),
                    "sha256": sha(data), "size_bytes": len(data), "url": url,
                    "content_type": headers.get("Content-Type"),
                })
                merged.extend(feats)
                if not feats:
                    break
                offset += len(feats)
                page_no += 1

            fc = {"type": "FeatureCollection", "features": merged}
            merged_bytes = json.dumps(fc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            merged_path = layer_dir / "merged.geojson"
            merged_path.write_bytes(merged_bytes)
            ids = [f.get("properties", {}).get("OBJECTID") for f in merged]
            dup_ids = len(ids) - len(set(ids))
            rec["merged"] = {
                "path": str(merged_path), "sha256": sha(merged_bytes),
                "feature_count": len(merged), "duplicate_objectid_count": dup_ids,
            }
            rec["arithmetic_closed"] = len(merged) == expected
            rec["state"] = "PASS_BYTES_FROZEN" if rec["arithmetic_closed"] and dup_ids == 0 else "FAIL_ARITHMETIC"
        except Exception as exc:
            rec["state"] = "BLOCKED"
            rec["error"] = repr(exc)
        manifest["layers"].append(rec)

    passed = sum(r["state"] == "PASS_BYTES_FROZEN" for r in manifest["layers"])
    manifest["pass_count"] = passed
    manifest["layer_count"] = len(LAYERS)
    manifest["certification"] = "PASS_SOURCE_MANIFESTATIONS_ONLY" if passed == len(LAYERS) else "OPEN"
    path = out / "sige_rest_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(path), "sha256": sha(path.read_bytes()), "pass_count": passed, "layer_count": len(LAYERS), "certification": manifest["certification"]}, indent=2))
    return 0 if passed == len(LAYERS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
