#!/usr/bin/env python3
"""Freeze NOAA NSDE app.js and extract data/distribution endpoint candidates.

This is discovery only. Strings, URLs, service names, and AJAX endpoints from
client code are candidate acquisition surfaces, never evidence that a dataset
exists or covers Puerto Rico. The raw JS bytes are frozen and hashed first.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://nsde.ngs.noaa.gov/app.js"
UA = "spiderweb-pr-nsde-app-discovery/1.0 (+https://github.com/jotaele44/spiderweb-pr)"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(b: bytes):
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/noaa_nsde_app")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        headers = dict(r.headers.items())
    js = out / "app.js"
    js.write_bytes(data)
    text = data.decode("utf-8", errors="replace")

    absolute = sorted(set(re.findall(r'https?://[^\s\"\'<>]+', text)))
    quoted_paths = sorted(set(
        x for x in re.findall(r'[\"\']([^\"\']+)[\"\']', text)
        if any(k in x.lower() for k in (".php", ".json", ".geojson", ".zip", "wms", "wfs", "tiles", "api", "shore", "cusp", "project", "download"))
    ))
    service_tokens = sorted(set(re.findall(r'\b(?:https?://)?[A-Za-z0-9._/-]*(?:FeatureServer|MapServer|geoserver|wfs|wms)[A-Za-z0-9?&=._%:/-]*', text, re.I)))
    ajax_contexts = []
    for m in re.finditer(r'(?:ajax|fetch|getJSON|XMLHttpRequest|download|source|tiles)', text, re.I):
        lo=max(0,m.start()-180); hi=min(len(text),m.end()+320)
        snippet=re.sub(r'\s+',' ',text[lo:hi]).strip()
        if snippet not in ajax_contexts:
            ajax_contexts.append(snippet)
        if len(ajax_contexts) >= 200:
            break

    manifest = {
        "schema_version": "1.0",
        "generated_utc": now(),
        "source": {
            "url": URL,
            "path": str(js),
            "size_bytes": len(data),
            "sha256": sha(data),
            "content_type": headers.get("Content-Type"),
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
        },
        "absolute_urls": absolute,
        "quoted_endpoint_candidates": quoted_paths,
        "service_tokens": service_tokens,
        "keyword_contexts": ajax_contexts,
        "rules": {
            "discovery_only": "client-code endpoint strings are candidates, not source existence/coverage proof",
            "no_identity": "no endpoint discovery may promote insular identity",
        },
        "certification": {"NSDE_APP_DISCOVERY":"PASS_BYTES_FROZEN", "GEOMETRIC_CURRENT":"OPEN", "CURRENT_PR_ARCHIPELAGO":"OPEN"}
    }
    mp=out/"nsde_app_discovery_manifest.json"
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"manifest":str(mp),"sha256":sha(mp.read_bytes()),"absolute_url_count":len(absolute),"quoted_candidate_count":len(quoted_paths),"service_token_count":len(service_tokens)},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
