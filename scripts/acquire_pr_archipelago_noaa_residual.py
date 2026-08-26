#!/usr/bin/env python3
"""Freeze NOAA Southeast Caribbean shoreline residual without re-fetching passed sources."""

from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

URL = "https://geodesy.noaa.gov/dist_shoreline/Southeast_Caribbean.zip"
UA = "spiderweb-pr-noaa-residual/1.0 (+https://github.com/jotaele44/spiderweb-pr)"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/geometry_snapshots/noaa_residual")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
        headers = dict(r.headers.items())
    path = out / "Southeast_Caribbean.zip"
    path.write_bytes(data)

    members = []
    if zipfile.is_zipfile(path):
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

    manifest = {
        "schema_version": "1.0",
        "source_family": "NOAA_NGS_NSDE",
        "scope": "Southeast Caribbean shoreline residual",
        "retrieval_utc": now(),
        "url": URL,
        "local_path": str(path),
        "size_bytes": len(data),
        "sha256": sha(data),
        "content_type": headers.get("Content-Type"),
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
        "archive_member_count": len(members),
        "archive_members": members,
        "state": "PASS_BYTES_FROZEN" if members else "BLOCKED_NOT_ZIP",
        "certification": {
            "GEOMETRIC_CURRENT": "OPEN",
            "CURRENT_PR_ARCHIPELAGO": "OPEN",
            "note": "shoreline source manifestation only; archive contents require geometry/schema inspection and reconciliation",
        },
    }
    mp = out / "noaa_residual_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(mp), "sha256": sha(mp.read_bytes()), "state": manifest["state"], "archive_member_count": len(members)}, indent=2))
    return 0 if members else 2


if __name__ == "__main__":
    raise SystemExit(main())
