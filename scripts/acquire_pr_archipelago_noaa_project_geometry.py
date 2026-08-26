#!/usr/bin/env python3
"""Freeze exact NOAA NSDE project archives for the bounded PR project set.

The endpoint contract is derived from frozen NSDE app.js:
  CMP feature.properties.id -> https://nsde.ngs.noaa.gov/downloads/<id>.zip

No filename guessing, project-name normalization, or proximity discovery is
used. Each response is frozen before validation. A non-ZIP response is a
blocked distribution manifestation, not evidence of geometry absence.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://nsde.ngs.noaa.gov/downloads/"
UA = "spiderweb-pr-noaa-project-geometry/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
PROJECTS = [
    "PR1401A-TB-N", "PR1401B-TB-N", "PR1401C-TB-N", "PR1401D-TB-N",
    "PR1502-CS-N", "PR1503-CS-N",
    "PR1801A-TB-C", "PR1801B-TB-C", "PR1801C-TB-C", "PR1801D-TB-C", "PR1801E-TB-C",
    "PR2001-CS-T", "PR2002-CS-T", "PR2003-CS-T", "PR2401-CS-T",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, timeout: int = 120) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers.items())


def classify_member(name: str) -> str:
    ext = Path(name).suffix.lower()
    return {
        ".shp": "SHP",
        ".shx": "SHX",
        ".dbf": "DBF",
        ".prj": "PRJ",
        ".cpg": "CPG",
        ".xml": "XML",
        ".geojson": "GEOJSON",
        ".json": "JSON",
        ".gpkg": "GPKG",
        ".gdb": "GDB_MEMBER",
        ".txt": "TEXT",
        ".pdf": "PDF",
    }.get(ext, ext.lstrip(".").upper() or "NO_EXTENSION")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/noaa_project_geometry")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "1.0",
        "generated_utc": now(),
        "source_family": "NOAA_NSDE_CMP_EXACT_DOWNLOAD",
        "endpoint_contract": "frozen NSDE app.js: cmpdl + feature.properties.id + '.zip'",
        "expected_project_count": len(PROJECTS),
        "projects": [],
        "rules": {
            "project_identity": "project code comes from previously bounded NOAA project metadata denominator",
            "response": "freeze response bytes before ZIP validation",
            "non_zip": "blocked distribution manifestation; never geometry absence",
            "member_identity": "archive members retain outer archive + member path + member SHA256",
            "canonical_identity": "archive/project membership never proves canonical insular-feature identity",
        },
        "certification": {"GEOMETRIC_CURRENT": "OPEN", "CURRENT_PR_ARCHIPELAGO": "OPEN"},
    }

    for code in PROJECTS:
        url = BASE + code + ".zip"
        path = out / f"{code}.zip"
        rec = {"project_code": code, "url": url, "retrieval_utc": now()}
        try:
            data, headers = fetch(url)
            path.write_bytes(data)
            rec.update({
                "path": str(path),
                "size_bytes": len(data),
                "sha256": sha_bytes(data),
                "content_type": headers.get("Content-Type"),
                "etag": headers.get("ETag"),
                "last_modified": headers.get("Last-Modified"),
            })
            if not zipfile.is_zipfile(path):
                rec["state"] = "BLOCKED_NOT_ZIP"
                rec["archive_member_count"] = 0
            else:
                members = []
                type_counts: dict[str, int] = {}
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        payload = zf.read(info)
                        mtype = classify_member(info.filename)
                        type_counts[mtype] = type_counts.get(mtype, 0) + 1
                        members.append({
                            "path": info.filename,
                            "type": mtype,
                            "compressed_size": info.compress_size,
                            "uncompressed_size": info.file_size,
                            "sha256": sha_bytes(payload),
                        })
                rec["state"] = "PASS_ARCHIVE_FROZEN"
                rec["archive_member_count"] = len(members)
                rec["member_type_counts"] = type_counts
                rec["archive_members"] = members
        except Exception as exc:
            rec.update({"state": "BLOCKED_TRANSPORT", "error": repr(exc), "archive_member_count": 0})
        manifest["projects"].append(rec)

    states: dict[str, int] = {}
    for p in manifest["projects"]:
        states[p["state"]] = states.get(p["state"], 0) + 1
    manifest["state_counts"] = states
    manifest["pass_archive_count"] = states.get("PASS_ARCHIVE_FROZEN", 0)
    manifest["blocked_count"] = len(PROJECTS) - manifest["pass_archive_count"]
    manifest["arithmetic_closed"] = len(manifest["projects"]) == len(PROJECTS) and sum(states.values()) == len(PROJECTS)
    manifest["state"] = "PASS_SOURCE_MANIFESTATION_ARITHMETIC" if manifest["arithmetic_closed"] else "FAIL"

    mp = out / "noaa_project_geometry_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "manifest": str(mp),
        "sha256": sha_bytes(mp.read_bytes()),
        "expected_project_count": len(PROJECTS),
        "pass_archive_count": manifest["pass_archive_count"],
        "blocked_count": manifest["blocked_count"],
        "state_counts": states,
        "arithmetic_closed": manifest["arithmetic_closed"],
    }, indent=2))
    return 0 if manifest["arithmetic_closed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
