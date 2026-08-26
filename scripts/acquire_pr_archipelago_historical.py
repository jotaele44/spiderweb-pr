#!/usr/bin/env python3
"""Freeze GNIS historical/alias manifestations for Puerto Rico independently.

This lane never mutates or fills the current denominator.  National topical
GNIS archives are frozen byte-for-byte, member hashes are recorded, and rows
that explicitly bind to Puerto Rico by source fields are preserved as a PR
subset for later temporal adjudication.  Names are manifestations, not IDs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

UA = "spiderweb-pr-archipelago-historical/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
BASE = "https://prd-tnm.s3.amazonaws.com/"
SOURCES = {
    "GNIS_HISTORICAL_FEATURES_NATIONAL": "StagedProducts/GeographicNames/Topical/HistoricalFeatures_National_Text.zip",
    "GNIS_ALL_NAMES_NATIONAL": "StagedProducts/GeographicNames/Topical/AllNames_National_Text.zip",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def freeze(url: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r, path.open("wb") as f:
        while True:
            block = r.read(1024 * 1024)
            if not block:
                break
            f.write(block)
        headers = dict(r.headers.items())
    members = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                h = hashlib.sha256()
                with zf.open(info) as src:
                    for b in iter(lambda: src.read(1024 * 1024), b""):
                        h.update(b)
                members.append({
                    "path": info.filename,
                    "uncompressed_size": info.file_size,
                    "compressed_size": info.compress_size,
                    "sha256": h.hexdigest(),
                })
    return {
        "url": url,
        "retrieval_utc": now(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
        "content_type": headers.get("Content-Type"),
        "local_path": str(path),
        "archive_members": members,
    }


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace("_", " ").split())


def _pr_row(row: dict[str, str]) -> bool:
    for k, v in row.items():
        nk = _norm(k)
        sv = (v or "").strip()
        if nk in {"state alpha", "state alpha code", "state"} and sv.upper() == "PR":
            return True
        if nk in {"state numeric", "state numeric code", "statefp"} and sv.zfill(2) == "72":
            return True
        if nk == "state name" and sv.casefold() == "puerto rico":
            return True
    return False


def parse_pr_rows(zip_path: Path, out_dir: Path) -> dict:
    candidates = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith((".txt", ".csv")):
                continue
            candidates.append(info)
        if not candidates:
            return {"state": "BLOCKED_NO_TEXT_MEMBER"}
        results = []
        for info in candidates:
            raw = zf.read(info)
            # GNIS topical text products are UTF-8/ASCII-compatible. Keep source
            # archive bytes frozen; decoded rows are a derived logical view.
            text = raw.decode("utf-8-sig", errors="replace")
            first = text.splitlines()[0] if text.splitlines() else ""
            delimiter = "|" if "|" in first else ","
            reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
            fields = reader.fieldnames or []
            rows = []
            total = 0
            for row in reader:
                total += 1
                if _pr_row(row):
                    rows.append(dict(row))
            results.append({
                "member_path": info.filename,
                "delimiter": delimiter,
                "fields": fields,
                "total_rows": total,
                "pr_rows": len(rows),
                "rows": rows,
            })
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (zip_path.stem + "_PR_rows.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "state": "PASS_PR_LOGICAL_VIEW",
        "path": str(out),
        "sha256": sha256_file(out),
        "member_results": [{k: v for k, v in r.items() if k != "rows"} for r in results],
        "pr_row_total": sum(r["pr_rows"] for r in results),
        "certification_note": "PR row selection is an explicit source-field filter; rows remain historical/name manifestations and do not modify current canonical identity.",
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/historical_snapshots")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "generated_utc": now(),
        "scope": "GNIS historical and alias manifestations; independent of current denominator",
        "sources": {},
        "certification": {
            "GNIS_HISTORICAL_MANIFESTATIONS": "OPEN",
            "HISTORICAL_ARCHIPELAGO_EXHAUSTION": "OPEN",
            "CURRENT_PR_ARCHIPELAGO": "UNCHANGED_OPEN",
        },
    }
    for source_id, key in SOURCES.items():
        url = BASE + urllib.parse.quote(key, safe="/")
        target = out / Path(key).name
        try:
            frozen = freeze(url, target)
            view = parse_pr_rows(target, out / "derived_pr_views")
            manifest["sources"][source_id] = {"state": "PASS_BYTES_FROZEN", "snapshot": frozen, "pr_view": view}
        except Exception as exc:
            manifest["sources"][source_id] = {"state": "BLOCKED", "error": repr(exc)}
    if all(v.get("state") == "PASS_BYTES_FROZEN" for v in manifest["sources"].values()):
        manifest["certification"]["GNIS_HISTORICAL_MANIFESTATIONS"] = "PASS_SOURCE_FAMILY_ONLY"
    path = out / "historical_source_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "manifest": str(path),
        "sha256": sha256_file(path),
        "states": {k: v.get("state") for k, v in manifest["sources"].items()},
        "pr_rows": {k: v.get("pr_view", {}).get("pr_row_total") for k, v in manifest["sources"].items()},
        "certification": manifest["certification"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
