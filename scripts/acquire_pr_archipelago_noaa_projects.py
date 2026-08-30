#!/usr/bin/env python3
"""Freeze the NOAA NGS Puerto Rico shoreline project denominator.

Discovery is link-local: an InPort child is accepted only when its own link title
contains a Puerto Rico project code (PR####...) and either spells out Puerto
Rico or uses the Puerto Rico jurisdiction token `, PR`. No nearby-window or
proximity heuristic is permitted.

Metadata, completion reports, and guessed direct ZIP manifestations are kept
separate. Viewer-only distribution or failed ZIP probes never establish source
absence. Project extents are metadata scopes, never land polygons.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PARENT = "https://www.fisheries.noaa.gov/inport/item/59091/full-list"
UA = "spiderweb-pr-noaa-projects/1.1 (+https://github.com/jotaele44/spiderweb-pr)"
ANCHOR_RE = re.compile(r'href="/inport/item/(\d+)"[^>]*>(.*?)</a>', re.I | re.S)
CODE_RE = re.compile(r"\b(PR\d{4}[A-Z]?(?:-[A-Z0-9]+)+)\b", re.I)


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


def pdf_probe(urls: list[str], path: Path) -> dict:
    attempts = []
    for url in urls:
        rec = freeze(url, path)
        attempts.append(rec)
        if rec.get("state") != "PASS_BYTES_FROZEN":
            continue
        data = path.read_bytes()
        if data.startswith(b"%PDF-"):
            rec["state"] = "PASS_PDF_FROZEN"
            rec["attempts"] = attempts
            return rec
        rec["state"] = "BLOCKED_NOT_PDF"
    return {"state": "BLOCKED", "attempts": attempts}


def zip_probe(url: str, path: Path) -> dict:
    rec = freeze(url, path)
    if rec["state"] != "PASS_BYTES_FROZEN":
        return rec
    if not zipfile.is_zipfile(path):
        rec["state"] = "BLOCKED_NOT_ZIP"
        return rec
    members = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            payload = zf.read(info)
            members.append({
                "path": info.filename,
                "uncompressed_size": info.file_size,
                "compressed_size": info.compress_size,
                "sha256": sha(payload),
            })
    rec["state"] = "PASS_ARCHIVE_FROZEN"
    rec["archive_member_count"] = len(members)
    rec["archive_members"] = members
    return rec


def discover_projects(text: str) -> list[dict]:
    projects: dict[str, dict] = {}
    rejected = []
    for item_id, raw_anchor in ANCHOR_RE.findall(text):
        title = html.unescape(re.sub(r"<[^>]+>", "", raw_anchor))
        title = re.sub(r"\s+", " ", title).strip()
        m = CODE_RE.search(title)
        if not m:
            continue
        code = m.group(1).upper()
        if not ("PUERTO RICO" in title.upper() or re.search(r",\s*PR(?:\s*,|\s*$)", title, re.I)):
            rejected.append({"item_id": int(item_id), "project_code": code, "title": title, "reason": "TITLE_NOT_PR_JURISDICTION"})
            continue
        candidate = {"item_id": int(item_id), "project_code": code, "title": title}
        prior = projects.get(code)
        if prior and prior != candidate:
            # Exact duplicate project-code manifestations must remain visible.
            prior.setdefault("duplicate_catalog_manifestations", []).append(candidate)
        else:
            projects.setdefault(code, candidate)
    rows = sorted(projects.values(), key=lambda x: x["project_code"])
    return rows, rejected


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/noaa_projects")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    parent_b, parent_h = fetch(PARENT, timeout=90)
    parent_path = out / "ngs_shoreline_parent_full_list.html"
    parent_path.write_bytes(parent_b)
    text = parent_b.decode("utf-8", errors="replace")
    projects, rejected = discover_projects(text)

    manifest = {
        "schema_version": "1.1",
        "generated_utc": now(),
        "source_family": "NOAA_NGS_SHORELINE",
        "parent_catalog": {
            "url": PARENT,
            "path": str(parent_path),
            "size_bytes": len(parent_b),
            "sha256": sha(parent_b),
            "content_type": parent_h.get("Content-Type"),
        },
        "projects": [],
        "rejected_catalog_candidates": rejected,
        "rules": {
            "discovery": "item link title must itself carry PR project code and Puerto Rico jurisdiction evidence",
            "project_extent": "metadata scope only; never promoted to land geometry",
            "viewer_only_distribution": "does not establish geometry absence",
            "zip_probe": "successful archive is source manifestation only; failed probe is not absence",
            "pdf_validation": "completion report requires PDF magic; HTML error payload is retained as failed manifestation",
        },
        "certification": {"GEOMETRIC_CURRENT": "OPEN", "CURRENT_PR_ARCHIPELAGO": "OPEN"},
    }

    for p in projects:
        item = str(p["item_id"])
        code = p["project_code"]
        pdir = out / code
        pdir.mkdir(parents=True, exist_ok=True)
        rec = dict(p)
        rec["inport_xml"] = freeze(
            f"https://www.fisheries.noaa.gov/inportserve/waf/noaa/nos/ngs/inport-xml/xml/{item}.xml",
            pdir / f"{item}.inport.xml",
        )
        rec["iso19115"] = freeze(
            f"https://www.fisheries.noaa.gov/inportserve/waf/noaa/nos/ngs/iso19115/xml/{item}.xml",
            pdir / f"{item}.iso19115.xml",
        )
        rec["completion_report"] = pdf_probe(
            [
                f"https://www.ngs.noaa.gov/desc_reports/{code}.pdf",
                f"https://www.ngs.noaa.gov/desc_reports/{code}.PDF",
            ],
            pdir / f"{code}.pdf",
        )
        probes = []
        for host in ("https://geodesy.noaa.gov", "https://www.ngs.noaa.gov"):
            for rel in (
                f"/dist_shoreline/{code}.zip",
                f"/dist_shoreline/{code}_Shoreline.zip",
                f"/dist_shoreline/{code.replace('-', '_')}.zip",
            ):
                url = host + rel
                probe_path = pdir / (host.split("//",1)[1].replace(".", "_") + "__" + rel.rsplit("/",1)[-1])
                probe = zip_probe(url, probe_path)
                probes.append(probe)
                if probe.get("state") == "PASS_ARCHIVE_FROZEN":
                    break
            if probes and probes[-1].get("state") == "PASS_ARCHIVE_FROZEN":
                break
        rec["geometry_zip_probes"] = probes
        rec["metadata_pass"] = rec["inport_xml"]["state"] == "PASS_BYTES_FROZEN" and rec["iso19115"]["state"] == "PASS_BYTES_FROZEN"
        rec["geometry_archive_pass"] = any(x.get("state") == "PASS_ARCHIVE_FROZEN" for x in probes)
        manifest["projects"].append(rec)

    codes = [x["project_code"] for x in manifest["projects"]]
    manifest["project_count"] = len(codes)
    manifest["unique_project_code_count"] = len(set(codes))
    manifest["duplicate_project_code_residue"] = len(codes) - len(set(codes))
    manifest["metadata_pass_count"] = sum(bool(x["metadata_pass"]) for x in manifest["projects"])
    manifest["completion_report_pass_count"] = sum(x["completion_report"].get("state") == "PASS_PDF_FROZEN" for x in manifest["projects"])
    manifest["geometry_archive_pass_count"] = sum(bool(x["geometry_archive_pass"]) for x in manifest["projects"])
    manifest["project_codes"] = codes
    manifest["state"] = (
        "PASS_PROJECT_DENOMINATOR_METADATA"
        if codes and manifest["metadata_pass_count"] == len(codes) and manifest["duplicate_project_code_residue"] == 0
        else "OPEN"
    )

    mp = out / "noaa_pr_project_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "manifest": str(mp),
        "sha256": sha(mp.read_bytes()),
        "project_count": manifest["project_count"],
        "project_codes": codes,
        "metadata_pass_count": manifest["metadata_pass_count"],
        "completion_report_pass_count": manifest["completion_report_pass_count"],
        "geometry_archive_pass_count": manifest["geometry_archive_pass_count"],
        "duplicate_project_code_residue": manifest["duplicate_project_code_residue"],
        "state": manifest["state"],
    }, indent=2))
    return 0 if manifest["state"] == "PASS_PROJECT_DENOMINATOR_METADATA" else 2


if __name__ == "__main__":
    raise SystemExit(main())
