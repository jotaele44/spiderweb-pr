#!/usr/bin/env python3
"""Freeze exact PR government WFS geometry control layers with bounded negotiation.

This residual acquirer does NOT re-fetch already-passed GNIS/Census evidence.
It probes WFS with resultType=hits first, then requests compressed SHAPE-ZIP
bytes for successful protocol forms. Request failure is never interpreted as
source absence. Every attempted URL/result is preserved in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

UA = "spiderweb-pr-prgov-wfs/1.1 (+https://github.com/jotaele44/spiderweb-pr)"
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
    ("1.1.0", "typeName"),
    ("1.0.0", "typeName"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, timeout: int) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def build_url(base: str, version: str, type_key: str, typename: str, **extra: str) -> str:
    p = {"service": "WFS", "version": version, "request": "GetFeature", type_key: typename}
    p.update(extra)
    return base + "?" + urllib.parse.urlencode(p)


def archive_inventory(path: Path) -> list[dict]:
    out = []
    if not zipfile.is_zipfile(path):
        return out
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            payload = zf.read(info)
            out.append({
                "path": info.filename,
                "uncompressed_size": info.file_size,
                "compressed_size": info.compress_size,
                "sha256": digest(payload),
            })
    return out


def looks_like_hits(data: bytes) -> bool:
    text = data[:4096].decode("utf-8", "replace").casefold()
    return "featurecollection" in text and ("numbermatched" in text or "numberoffeatures" in text)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/pr_gov_exact")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.1",
        "generated_utc": now(),
        "scope": "PR-government exact WFS residual acquisition only",
        "layers": [],
        "certification": "OPEN",
    }

    for typename in LAYERS:
        safe = typename.split(":", 1)[-1]
        layer = {"typename": typename, "attempts": [], "state": "BLOCKED"}
        accepted = None

        for base in BASES:
            for version, type_key in FORMS:
                hit_url = build_url(base, version, type_key, typename, resultType="hits")
                hit_attempt = {"stage": "hits", "url": hit_url, "version": version, "type_parameter": type_key}
                try:
                    hit_data, hit_headers = fetch(hit_url, timeout=12)
                    hit_attempt.update({
                        "http": "SUCCESS",
                        "size_bytes": len(hit_data),
                        "sha256": digest(hit_data),
                        "content_type": hit_headers.get("Content-Type"),
                        "looks_like_hits": looks_like_hits(hit_data),
                    })
                except Exception as exc:
                    hit_attempt.update({"http": "ERROR", "error": repr(exc)})
                    layer["attempts"].append(hit_attempt)
                    continue
                layer["attempts"].append(hit_attempt)
                if not hit_attempt["looks_like_hits"]:
                    continue

                zip_url = build_url(base, version, type_key, typename, outputFormat="SHAPE-ZIP")
                zip_attempt = {"stage": "shape_zip", "url": zip_url, "version": version, "type_parameter": type_key}
                try:
                    data, headers = fetch(zip_url, timeout=75)
                    path = out / f"{safe}.zip"
                    path.write_bytes(data)
                    members = archive_inventory(path)
                    zip_attempt.update({
                        "http": "SUCCESS",
                        "size_bytes": len(data),
                        "sha256": digest(data),
                        "content_type": headers.get("Content-Type"),
                        "archive_member_count": len(members),
                    })
                    if members:
                        hits_path = out / f"{safe}_hits.xml"
                        hits_path.write_bytes(hit_data)
                        accepted = {
                            "version": version,
                            "type_parameter": type_key,
                            "base": base,
                            "retrieval_utc": now(),
                            "hits": {
                                "url": hit_url,
                                "path": str(hits_path),
                                "size_bytes": len(hit_data),
                                "sha256": digest(hit_data),
                            },
                            "shape_zip": {
                                "url": zip_url,
                                "path": str(path),
                                "size_bytes": len(data),
                                "sha256": digest(data),
                                "content_type": headers.get("Content-Type"),
                                "archive_members": members,
                            },
                        }
                except Exception as exc:
                    zip_attempt.update({"http": "ERROR", "error": repr(exc)})
                layer["attempts"].append(zip_attempt)
                if accepted:
                    break
            if accepted:
                break

        if accepted:
            layer["state"] = "PASS_EXACT_SHAPEZIP_FROZEN"
            layer["accepted"] = accepted
        manifest["layers"].append(layer)

    passed = sum(x["state"] == "PASS_EXACT_SHAPEZIP_FROZEN" for x in manifest["layers"])
    manifest["pass_count"] = passed
    manifest["layer_count"] = len(LAYERS)
    manifest["certification"] = "PASS_CONTROL_LAYER_ACQUISITION" if passed == len(LAYERS) else "OPEN"
    path = out / "pr_gov_exact_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "manifest": str(path),
        "sha256": digest(path.read_bytes()),
        "pass_count": passed,
        "layer_count": len(LAYERS),
        "certification": manifest["certification"],
    }, indent=2))
    return 0 if passed == len(LAYERS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
