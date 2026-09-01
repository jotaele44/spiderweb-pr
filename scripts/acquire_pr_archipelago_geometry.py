#!/usr/bin/env python3
"""Acquire independent geometry-support manifestations for PR archipelago.

This stage is intentionally separate from GNIS naming acquisition. It discovers
provider versions from provider indexes rather than assuming a calendar-year
URL, freezes exact bytes, inventories archives, and emits candidate layer
manifests. Discovery remains non-canonical until geometry/identity adjudication.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

UA = "spiderweb-pr-archipelago/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
CENSUS_ROOT = "https://www2.census.gov/geo/tiger/"
PR_WFS_URLS = [
    "https://geoserver2.pr.gov/geoserver/pr_geodata/wfs",
    "http://geoserver2.pr.gov/geoserver/pr_geodata/wfs",
]
NSDE = "https://nsde.ngs.noaa.gov/"

# Exact local-authority geometry manifestations selected from the frozen WFS
# capabilities.  These are not interchangeable: one is a broad island/legal
# shape candidate, one is detailed areal hydrography, and one is an explicit
# known-incomplete shoreline negative control.
PR_WFS_CONTROL_LAYERS = [
    "pr_geodata:g03_legales_isla_pr",
    "pr_geodata:g23_mapa_base_hidrografia_areas_2023",
    "pr_geodata:g23_riesgo_inunda_shoreline_2017",
]


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get(url: str, timeout=120) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def freeze(url: str, out: Path) -> dict:
    data, headers = get(url)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    members = []
    if zipfile.is_zipfile(out):
        with zipfile.ZipFile(out) as zf:
            for i in zf.infolist():
                if i.is_dir():
                    continue
                with zf.open(i) as f:
                    payload = f.read()
                members.append({
                    "path": i.filename,
                    "uncompressed_size": i.file_size,
                    "compressed_size": i.compress_size,
                    "sha256": digest(payload),
                })
    return {
        "url": url,
        "retrieval_utc": now(),
        "local_path": str(out),
        "size_bytes": len(data),
        "sha256": digest(data),
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
        "content_type": headers.get("Content-Type"),
        "archive_members": members,
    }


def hrefs(html: str) -> list[str]:
    return re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)


def census(out: Path, manifest: dict) -> None:
    root_bytes, _ = get(CENSUS_ROOT)
    root_html = root_bytes.decode("utf-8", "replace")
    years = sorted({int(y) for y in re.findall(r'TIGER(20\d{2})/', root_html)})
    manifest["census"]["available_years"] = years
    if not years:
        manifest["census"]["state"] = "BLOCKED_NO_YEAR_DISCOVERY"
        return
    year = max(years)
    manifest["census"]["selected_year"] = year
    manifest["census"]["selection_rule"] = "maximum provider-listed TIGER year"
    for layer in ["STATE", "COASTLINE"]:
        index_url = f"{CENSUS_ROOT}TIGER{year}/{layer}/"
        index_path = out / "census" / f"TIGER{year}_{layer}_index.html"
        try:
            frozen_index = freeze(index_url, index_path)
        except Exception as exc:
            manifest["census"][layer] = {"state": "BLOCKED_INDEX", "error": repr(exc)}
            continue
        text = index_path.read_text(encoding="utf-8", errors="replace")
        links = [x for x in hrefs(text) if x.lower().endswith(".zip")]
        exact = []
        for x in links:
            low = x.lower()
            if layer == "STATE" and re.search(r'_us_state\.zip$', low):
                exact.append(x)
            elif layer == "COASTLINE" and (re.search(r'_72_coastline\.zip$', low) or re.search(r'_us_coastline\.zip$', low)):
                exact.append(x)
        info = {
            "state": "PASS_INDEX_FROZEN",
            "index": frozen_index,
            "zip_links_total": len(links),
            "candidate_links": links,
            "exact_pr_or_national_candidates": exact,
            "downloads": [],
            "certification_note": "TIGER STATE is legal/administrative geometry and COASTLINE is linework; neither is promoted to a canonical land-feature denominator.",
        }
        for x in exact:
            url = urllib.parse.urljoin(index_url, x)
            info["downloads"].append(freeze(url, out / "census" / Path(urllib.parse.urlparse(url).path).name))
        if not exact:
            info["state"] = "OPEN_NO_EXACT_PR_OR_NATIONAL_CANDIDATE"
        manifest["census"][layer] = info
    manifest["census"]["state"] = (
        "PASS_SUPPORT_MANIFESTATIONS_FROZEN"
        if all(manifest["census"].get(x, {}).get("downloads") for x in ("STATE", "COASTLINE"))
        else "OPEN"
    )


def _wfs_url(base: str, **params: str) -> str:
    fixed = {"service": "WFS", "version": "2.0.0"}
    fixed.update(params)
    return base + "?" + urllib.parse.urlencode(fixed)


def _feature_type_metadata(root: ET.Element) -> list[dict]:
    rows = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] != "FeatureType":
            continue
        row = {}
        for c in elem:
            tag = c.tag.rsplit("}", 1)[-1]
            if tag in {"Name", "Title", "Abstract", "DefaultCRS", "SRS"}:
                row[tag.lower()] = c.text
            elif tag == "WGS84BoundingBox":
                low = next((x.text for x in c if x.tag.rsplit("}", 1)[-1] == "LowerCorner"), None)
                high = next((x.text for x in c if x.tag.rsplit("}", 1)[-1] == "UpperCorner"), None)
                row["wgs84_lower"] = low
                row["wgs84_upper"] = high
        if row.get("name"):
            rows.append(row)
    return rows


def _count_geojson(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        features = data.get("features", []) if isinstance(data, dict) else []
        geom_types = {}
        null_geometry = 0
        for f in features:
            geom = f.get("geometry") if isinstance(f, dict) else None
            if not geom:
                null_geometry += 1
                continue
            t = geom.get("type", "UNKNOWN")
            geom_types[t] = geom_types.get(t, 0) + 1
        return {
            "feature_count": len(features),
            "geometry_types": geom_types,
            "null_geometry_count": null_geometry,
        }
    except Exception as exc:
        return {"parse_state": "BLOCKED", "error": repr(exc)}


def pr_wfs(out: Path, manifest: dict) -> None:
    last_error = None
    frozen = None
    base_used = None
    for base in PR_WFS_URLS:
        url = _wfs_url(base, request="GetCapabilities")
        try:
            frozen = freeze(url, out / "pr_gov" / "pr_geodata_wfs_GetCapabilities.xml")
            base_used = base
            break
        except Exception as exc:
            last_error = repr(exc)
    if not frozen or not base_used:
        manifest["pr_gov_wfs"] = {"state": "BLOCKED", "error": last_error}
        return
    path = Path(frozen["local_path"])
    raw = path.read_bytes()
    try:
        root = ET.fromstring(raw)
        metadata = _feature_type_metadata(root)
        tokens = ("coast", "costa", "shore", "litoral", "agua", "water", "hydro", "hidro", "isla", "cayo", "isl")
        candidates = [
            x for x in metadata
            if any(t in ((x.get("name") or "") + " " + (x.get("title") or "")).casefold() for t in tokens)
        ]
        exact = []
        by_name = {x["name"]: x for x in metadata}
        for typename in PR_WFS_CONTROL_LAYERS:
            safe = typename.split(":", 1)[-1]
            layer = {"typename": typename, "capabilities_metadata": by_name.get(typename), "state": "OPEN"}
            try:
                hits_url = _wfs_url(base_used, request="GetFeature", typeNames=typename, resultType="hits")
                layer["hits"] = freeze(hits_url, out / "pr_gov" / f"{safe}_hits.xml")
                data_url = _wfs_url(base_used, request="GetFeature", typeNames=typename, outputFormat="application/json")
                layer["geojson"] = freeze(data_url, out / "pr_gov" / f"{safe}.geojson")
                layer["geojson_summary"] = _count_geojson(Path(layer["geojson"]["local_path"]))
                layer["state"] = "PASS_EXACT_LAYER_FROZEN"
            except Exception as exc:
                layer["state"] = "BLOCKED"
                layer["error"] = repr(exc)
            exact.append(layer)
        manifest["pr_gov_wfs"] = {
            "state": "PASS_CAPABILITIES_FROZEN",
            "snapshot": frozen,
            "base_url_used": base_used,
            "feature_type_count": len(metadata),
            "geometry_relevant_discovery_candidates": candidates,
            "candidate_count": len(candidates),
            "exact_control_layers": exact,
            "certification_note": "text-token filtering is discovery only; exact control layers are separately frozen but remain source manifestations, not canonical identities.",
        }
    except Exception as exc:
        manifest["pr_gov_wfs"] = {"state": "BLOCKED_PARSE", "snapshot": frozen, "error": repr(exc)}


def nsde(out: Path, manifest: dict) -> None:
    try:
        frozen = freeze(NSDE, out / "noaa_nsde" / "index.html")
        text = Path(frozen["local_path"]).read_text(encoding="utf-8", errors="replace")
        links = hrefs(text)
        manifest["noaa_nsde"] = {
            "state": "PASS_PORTAL_FROZEN",
            "snapshot": frozen,
            "links": links,
            "southeast_caribbean_candidate": next((x for x in links if "Southeast_Caribbean.zip" in x), None),
            "certification_note": "portal freeze only; vector geometry bytes remain OPEN until exact downloadable resources are resolved",
        }
    except Exception as exc:
        manifest["noaa_nsde"] = {"state": "BLOCKED", "error": repr(exc)}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.1",
        "generated_utc": now(),
        "scope": "independent geometry-source discovery and byte freeze",
        "census": {"state": "OPEN"},
        "pr_gov_wfs": {"state": "OPEN"},
        "noaa_nsde": {"state": "OPEN"},
        "certification": {"GEOMETRIC_CURRENT": "OPEN", "CURRENT_PR_ARCHIPELAGO": "OPEN"},
    }
    census(out, manifest)
    pr_wfs(out, manifest)
    nsde(out, manifest)
    path = out / "geometry_source_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(path), "sha256": digest(path.read_bytes()), "states": {
        "census": manifest["census"].get("state", "OPEN"),
        "pr_gov_wfs": manifest["pr_gov_wfs"].get("state"),
        "noaa_nsde": manifest["noaa_nsde"].get("state"),
        "GEOMETRIC_CURRENT": "OPEN",
    }}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
