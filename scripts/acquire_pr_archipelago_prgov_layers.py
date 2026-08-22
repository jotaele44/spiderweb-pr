#!/usr/bin/env python3
"""Freeze exact PR government WFS geometry control layers with negotiation.

The PR GeoServer advertises WFS 2.0 capabilities but some GetFeature parameter
forms return HTTP 400.  This client records every attempted protocol form and
accepts only an actual GeoJSON FeatureCollection.  It never interprets request
failure as source absence.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "spiderweb-pr-prgov-wfs/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
BASES = [
    "https://geoserver2.pr.gov/geoserver/pr_geodata/wfs",
    "http://geoserver2.pr.gov/geoserver/pr_geodata/wfs",
]
LAYERS = [
    "pr_geodata:g03_legales_isla_pr",
    "pr_geodata:g23_mapa_base_hidrografia_areas_2023",
    "pr_geodata:g23_riesgo_inunda_shoreline_2017",
]
FORMS = [
    ("2.0.0", "typeNames"),
    ("2.0.0", "typeName"),
    ("1.1.0", "typeName"),
    ("1.0.0", "typeName"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, timeout: int = 90) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def build_url(base: str, version: str, type_key: str, typename: str, *, hits: bool = False, output: str = "application/json") -> str:
    p = {"service": "WFS", "version": version, "request": "GetFeature", type_key: typename}
    if hits:
        p["resultType"] = "hits"
    else:
        p["outputFormat"] = output
    return base + "?" + urllib.parse.urlencode(p)


def valid_feature_collection(data: bytes) -> tuple[bool, dict]:
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception as exc:
        return False, {"reason": "NOT_JSON", "error": repr(exc)}
    if not isinstance(obj, dict) or obj.get("type") != "FeatureCollection" or not isinstance(obj.get("features"), list):
        return False, {"reason": "NOT_FEATURE_COLLECTION"}
    geom = {}
    nulls = 0
    for f in obj["features"]:
        g = f.get("geometry") if isinstance(f, dict) else None
        if not g:
            nulls += 1
            continue
        t = g.get("type", "UNKNOWN")
        geom[t] = geom.get(t, 0) + 1
    return True, {"feature_count": len(obj["features"]), "geometry_types": geom, "null_geometry_count": nulls}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/pr_gov_exact")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "1.0", "generated_utc": now(), "layers": [], "certification": "OPEN"}

    for typename in LAYERS:
        safe = typename.split(":", 1)[-1]
        layer = {"typename": typename, "attempts": [], "state": "BLOCKED"}
        accepted = None
        for base in BASES:
            for version, type_key in FORMS:
                for output_format in ("application/json", "json"):
                    url = build_url(base, version, type_key, typename, output=output_format)
                    attempt = {"url": url, "version": version, "type_parameter": type_key, "output_format": output_format}
                    try:
                        data, headers = fetch(url)
                        ok, summary = valid_feature_collection(data)
                        attempt.update({"http": "SUCCESS", "size_bytes": len(data), "sha256": digest(data), "validation": summary})
                        if ok:
                            path = out / f"{safe}.geojson"
                            path.write_bytes(data)
                            accepted = {
                                "url": url,
                                "retrieval_utc": now(),
                                "path": str(path),
                                "size_bytes": len(data),
                                "sha256": digest(data),
                                "content_type": headers.get("Content-Type"),
                                "summary": summary,
                            }
                            layer["attempts"].append(attempt)
                            break
                    except Exception as exc:
                        attempt.update({"http": "ERROR", "error": repr(exc)})
                    layer["attempts"].append(attempt)
                if accepted:
                    break
            if accepted:
                break
        if accepted:
            layer["state"] = "PASS_EXACT_GEOJSON_FROZEN"
            layer["accepted"] = accepted
            # Hits is supplemental and never allowed to invalidate valid bytes.
            hit_attempts = []
            for version, type_key in FORMS:
                url = build_url(accepted["url"].split("?", 1)[0], version, type_key, typename, hits=True)
                try:
                    data, headers = fetch(url)
                    hp = out / f"{safe}_hits.xml"
                    hp.write_bytes(data)
                    layer["hits"] = {"url": url, "retrieval_utc": now(), "path": str(hp), "size_bytes": len(data), "sha256": digest(data), "content_type": headers.get("Content-Type")}
                    break
                except Exception as exc:
                    hit_attempts.append({"url": url, "error": repr(exc)})
            if hit_attempts:
                layer["hit_attempt_failures"] = hit_attempts
        manifest["layers"].append(layer)

    passed = sum(x["state"] == "PASS_EXACT_GEOJSON_FROZEN" for x in manifest["layers"])
    manifest["pass_count"] = passed
    manifest["layer_count"] = len(LAYERS)
    manifest["certification"] = "PASS_CONTROL_LAYER_ACQUISITION" if passed == len(LAYERS) else "OPEN"
    path = out / "pr_gov_exact_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(path), "sha256": digest(path.read_bytes()), "pass_count": passed, "layer_count": len(LAYERS), "certification": manifest["certification"]}, indent=2))
    return 0 if passed == len(LAYERS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
