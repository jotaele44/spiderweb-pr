#!/usr/bin/env python3
"""Freeze NOAA NGS historical Puerto Rico shoreline manifestations independently.

Only Shoreline Data Rescue records whose own NOAA catalog-link title binds them
to Puerto Rico are admitted. This lane never mutates, fills, or certifies the
current A denominator. Historical names/geometries remain independent source
manifestations until temporal/identity adjudication.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PARENT = "https://www.fisheries.noaa.gov/inport/item/59091/full-list"
UA = "spiderweb-pr-noaa-historical/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
ANCHOR_RE = re.compile(r'href="/inport/item/(\d+)"[^>]*>(.*?)</a>', re.I | re.S)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, timeout: int = 60) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def freeze(url: str, path: Path) -> dict:
    try:
        data, headers = fetch(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {
            "url": url,
            "state": "PASS_BYTES_FROZEN",
            "path": str(path),
            "size_bytes": len(data),
            "sha256": sha(data),
            "content_type": headers.get("Content-Type"),
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
        }
    except Exception as exc:
        return {"url": url, "state": "BLOCKED", "error": repr(exc)}


def clean_title(raw: str) -> str:
    title = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\s+", " ", title).strip()


def is_pr_historical(title: str) -> bool:
    up = title.upper()
    if "SHORELINE DATA RESCUE PROJECT" not in up:
        return False
    return "PUERTO RICO" in up or bool(re.search(r",\s*PR(?:\s*,|\s*$)", title, re.I))


def project_code(title: str) -> str | None:
    # Historical rescue identifiers are heterogeneous: PH####, PR####A/B, etc.
    parts = [p.strip(" ,.;:()") for p in title.split()]
    for token in reversed(parts):
        if re.fullmatch(r"(?:PH|PR)\d{4}[A-Z0-9]*", token, re.I):
            return token.upper()
    return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/historical_snapshots/noaa_shoreline")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    parent_b, parent_h = fetch(PARENT, timeout=90)
    parent_path = out / "ngs_shoreline_parent_full_list.html"
    parent_path.write_bytes(parent_b)

    discovered = []
    for item_id, raw_title in ANCHOR_RE.findall(parent_b.decode("utf-8", errors="replace")):
        title = clean_title(raw_title)
        if not is_pr_historical(title):
            continue
        discovered.append({
            "item_id": int(item_id),
            "title": title,
            "project_code": project_code(title),
        })

    # The same catalog item may appear in more than one rendered hierarchy link.
    unique = {}
    for row in discovered:
        key = (row["item_id"], row["title"])
        unique[key] = row
    rows = sorted(unique.values(), key=lambda x: (x.get("project_code") or "", x["item_id"]))

    manifest = {
        "schema_version": "1.0",
        "generated_utc": now(),
        "scope": "NOAA NGS historical Shoreline Data Rescue manifestations explicitly bound to Puerto Rico by their own catalog title",
        "parent_catalog": {
            "url": PARENT,
            "path": str(parent_path),
            "size_bytes": len(parent_b),
            "sha256": sha(parent_b),
            "content_type": parent_h.get("Content-Type"),
        },
        "records": [],
        "rules": {
            "current_contamination": "forbidden; this lane never fills A",
            "identity": "historical project/title/extent does not establish current canonical identity",
            "discovery": "same-link-title Puerto Rico evidence only; no nearby-window heuristic",
        },
        "certification": {
            "NOAA_HISTORICAL_SHORELINE_MANIFESTATIONS": "OPEN",
            "HISTORICAL_ARCHIPELAGO_EXHAUSTION": "OPEN",
            "CURRENT_PR_ARCHIPELAGO": "UNCHANGED_OPEN"
        }
    }

    for row in rows:
        item = str(row["item_id"])
        code = row.get("project_code") or f"ITEM_{item}"
        rdir = out / code
        rec = dict(row)
        rec["inport_xml"] = freeze(
            f"https://www.fisheries.noaa.gov/inportserve/waf/noaa/nos/ngs/inport-xml/xml/{item}.xml",
            rdir / f"{item}.inport.xml",
        )
        rec["iso19115"] = freeze(
            f"https://www.fisheries.noaa.gov/inportserve/waf/noaa/nos/ngs/iso19115/xml/{item}.xml",
            rdir / f"{item}.iso19115.xml",
        )
        rec["metadata_pass"] = rec["inport_xml"].get("state") == "PASS_BYTES_FROZEN" and rec["iso19115"].get("state") == "PASS_BYTES_FROZEN"
        manifest["records"].append(rec)

    manifest["record_count"] = len(manifest["records"])
    manifest["metadata_pass_count"] = sum(bool(x["metadata_pass"]) for x in manifest["records"])
    manifest["unique_item_id_count"] = len({x["item_id"] for x in manifest["records"]})
    if manifest["record_count"] and manifest["metadata_pass_count"] == manifest["record_count"]:
        manifest["certification"]["NOAA_HISTORICAL_SHORELINE_MANIFESTATIONS"] = "PASS_SOURCE_FAMILY_ONLY"

    mp = out / "noaa_historical_shoreline_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "manifest": str(mp),
        "sha256": sha(mp.read_bytes()),
        "record_count": manifest["record_count"],
        "metadata_pass_count": manifest["metadata_pass_count"],
        "project_codes": [x.get("project_code") for x in manifest["records"]],
        "certification": manifest["certification"]
    }, ensure_ascii=False, indent=2))
    return 0 if manifest["metadata_pass_count"] == manifest["record_count"] and manifest["record_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
