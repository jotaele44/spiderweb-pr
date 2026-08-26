#!/usr/bin/env python3
"""Acquire and freeze authoritative PR archipelago source manifestations.

The script is deliberately restartable and fail-closed. It resolves mutable
provider directory listings at run time, records the exact selected object key,
downloads bytes once per snapshot directory, computes SHA256, inventories
archives, and emits a machine-readable manifest. It does not assert canonical
identity from names, counts, nearest features, or source taxonomy.

Current acquisition vectors:
  A1 USGS/BGN GNIS DomesticNames + FullModel Puerto Rico products
  A2 NOAA NGS Puerto Rico shoreline metadata manifests (project-level)
  A3 Census TIGER/Line Puerto Rico/state geometry support manifests

Historical/topical GNIS acquisition is intentionally separate from the current
named denominator; use --historical to fetch those national topical products.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

USER_AGENT = "spiderweb-pr-archipelago/1.0 (+https://github.com/jotaele44/spiderweb-pr)"
TNM_BUCKET = "https://prd-tnm.s3.amazonaws.com"
GNIS_PREFIXES = {
    "gnis_domestic": "StagedProducts/GeographicNames/DomesticNames/",
    "gnis_fullmodel": "StagedProducts/GeographicNames/FullModel/",
}
GNIS_HISTORICAL = {
    "gnis_historical_features": "StagedProducts/GeographicNames/Topical/HistoricalFeatures_National_Text.zip",
    "gnis_all_names": "StagedProducts/GeographicNames/Topical/AllNames_National_Text.zip",
}
NOAA_INPORT_IDS = {
    "noaa_ngs_west_legacy": 60847,
    "noaa_ngs_north": 63492,
    "noaa_ngs_culebra_vieques": 71219,
    "noaa_ngs_south": 71306,
    "noaa_ngs_west_current": 71771,
}
NOAA_WAF = "https://www.fisheries.noaa.gov/inportserve/waf/noaa/nos/ngs/inport-xml/xml/{item_id}.xml"
CENSUS_CANDIDATES = {
    # Exact current year is discovered independently in the manifest; these
    # stable directory/index URLs freeze the provider manifestation without
    # claiming that any one TIGER layer is a complete island denominator.
    "census_tiger_root": "https://www2.census.gov/geo/tiger/",
    "census_tiger_2026_index": "https://www2.census.gov/geo/tiger/TIGER2026/",
    "census_tiger_2026_state": "https://www2.census.gov/geo/tiger/TIGER2026/STATE/",
    "census_tiger_2026_coastline": "https://www2.census.gov/geo/tiger/TIGER2026/COASTLINE/",
}


@dataclass
class FrozenObject:
    source_family: str
    url: str
    resolved_key: str | None
    retrieval_utc: str
    size_bytes: int
    sha256: str
    content_type: str | None
    etag: str | None
    local_path: str
    archive_members: list[dict]
    notes: list[str]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request(url: str, *, method: str = "GET", timeout: int = 120):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def archive_inventory(path: Path) -> list[dict]:
    if not zipfile.is_zipfile(path):
        return []
    out = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            h = hashlib.sha256()
            with zf.open(info) as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(block)
            out.append({
                "path": info.filename,
                "uncompressed_size": info.file_size,
                "compressed_size": info.compress_size,
                "sha256": h.hexdigest(),
            })
    return out


def freeze_url(source_family: str, url: str, out_dir: Path, *, resolved_key: str | None = None) -> FrozenObject:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urllib.parse.urlparse(url).path).name or f"{source_family}.html"
    path = out_dir / name
    retrieval = utcnow()
    notes: list[str] = []
    if not path.exists():
        with request(url) as resp, path.open("wb") as f:
            while True:
                block = resp.read(1024 * 1024)
                if not block:
                    break
                f.write(block)
            content_type = resp.headers.get("Content-Type")
            etag = resp.headers.get("ETag")
    else:
        content_type = None
        etag = None
        notes.append("REUSED_EXISTING_SNAPSHOT_BYTES")
    return FrozenObject(
        source_family=source_family,
        url=url,
        resolved_key=resolved_key,
        retrieval_utc=retrieval,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        content_type=content_type,
        etag=etag,
        local_path=str(path),
        archive_members=archive_inventory(path),
        notes=notes,
    )


def list_s3(prefix: str) -> list[dict]:
    """Return the complete S3 object listing for prefix, paging if needed."""
    rows: list[dict] = []
    token = None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        url = TNM_BUCKET + "/?" + urllib.parse.urlencode(params)
        with request(url) as resp:
            root = ET.fromstring(resp.read())
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        for content in root.findall("s3:Contents", ns):
            rows.append({
                "key": content.findtext("s3:Key", namespaces=ns),
                "last_modified": content.findtext("s3:LastModified", namespaces=ns),
                "etag": content.findtext("s3:ETag", namespaces=ns),
                "size": int(content.findtext("s3:Size", default="0", namespaces=ns)),
            })
        truncated = root.findtext("s3:IsTruncated", default="false", namespaces=ns).lower() == "true"
        if not truncated:
            break
        token = root.findtext("s3:NextContinuationToken", namespaces=ns)
        if not token:
            raise RuntimeError("S3 listing says truncated but supplied no continuation token")
    return rows


def is_pr_gnis_key(key: str) -> bool:
    name = Path(key).name.lower()
    signals = ("puerto_rico", "puertorico", "_pr_", "_72_", "-pr-", "_pr.", "_pr-")
    return any(s in name for s in signals)


def select_pr_gnis(objects: list[dict], family: str) -> list[dict]:
    candidates = [o for o in objects if o["key"].lower().endswith(".zip") and is_pr_gnis_key(o["key"])]
    if not candidates:
        # Fail closed: preserve the listing and force operator review rather than
        # silently selecting a national file or a nearest-name candidate.
        return []
    # Multiple formats (GDB/GPKG/TXT) are valid independent manifestations.
    # Keep all PR-specific candidates, sorted by key for deterministic output.
    return sorted(candidates, key=lambda x: x["key"])


def freeze_gnis(out_dir: Path, manifest: dict) -> None:
    for family, prefix in GNIS_PREFIXES.items():
        objects = list_s3(prefix)
        listing_path = out_dir / f"{family}_s3_listing.json"
        listing_path.write_text(json.dumps(objects, indent=2, sort_keys=True), encoding="utf-8")
        listing_obj = FrozenObject(
            source_family=family + "_directory_listing",
            url=TNM_BUCKET + "/?" + urllib.parse.urlencode({"list-type": "2", "prefix": prefix}),
            resolved_key=prefix,
            retrieval_utc=utcnow(),
            size_bytes=listing_path.stat().st_size,
            sha256=sha256_file(listing_path),
            content_type="application/json; derived from provider XML listing",
            etag=None,
            local_path=str(listing_path),
            archive_members=[],
            notes=["DERIVED_CANONICAL_SERIALIZATION_OF_PROVIDER_DIRECTORY_LISTING"],
        )
        manifest["objects"].append(asdict(listing_obj))
        selected = select_pr_gnis(objects, family)
        manifest["discoveries"][family] = {
            "prefix": prefix,
            "object_count": len(objects),
            "pr_candidate_count": len(selected),
            "selected_keys": [o["key"] for o in selected],
            "state": "PASS" if selected else "BLOCKED_NO_PR_SPECIFIC_OBJECT_MATCH",
        }
        for obj in selected:
            url = TNM_BUCKET + "/" + urllib.parse.quote(obj["key"], safe="/")
            frozen = freeze_url(family, url, out_dir / family, resolved_key=obj["key"])
            manifest["objects"].append(asdict(frozen))


def find_text_member(zip_path: Path) -> Path | None:
    if not zipfile.is_zipfile(zip_path):
        return None
    with zipfile.ZipFile(zip_path) as zf:
        members = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith((".txt", ".csv"))]
        if not members:
            return None
        member = sorted(members, key=lambda x: x.file_size, reverse=True)[0]
        target = zip_path.with_suffix("") / Path(member.filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with zf.open(member) as src, target.open("wb") as dst:
                dst.write(src.read())
        return target


def inspect_domestic_names(out_dir: Path, manifest: dict) -> None:
    family_dir = out_dir / "gnis_domestic"
    if not family_dir.exists():
        manifest["named_current"] = {"state": "BLOCKED", "reason": "no DomesticNames bytes"}
        return
    candidates = []
    for z in family_dir.glob("*.zip"):
        txt = find_text_member(z)
        if txt:
            candidates.append((z, txt))
    if not candidates:
        manifest["named_current"] = {"state": "BLOCKED", "reason": "no parseable pipe-delimited DomesticNames member"}
        return
    # Preserve every candidate parse separately. Do not aggregate across source
    # manifestations because that could synthesize duplicate records.
    parsed = []
    for z, txt in candidates:
        with txt.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.readline()
            delimiter = "|" if "|" in sample else ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delimiter)
            fields = reader.fieldnames or []
            feature_class_field = next((x for x in fields if x.lower().replace("_", " ") in {"feature class", "featureclass"}), None)
            feature_id_field = next((x for x in fields if x.lower().replace("_", " ") in {"feature id", "featureid"}), None)
            name_field = next((x for x in fields if x.lower().replace("_", " ") in {"feature name", "feature name official", "feature_name", "name"}), None)
            state_field = next((x for x in fields if x.lower().replace("_", " ") in {"state alpha", "state alpha code", "state_alpha", "state"}), None)
            row_count = 0
            island_rows = []
            ids = []
            duplicates = set()
            for row in reader:
                row_count += 1
                cls = (row.get(feature_class_field, "") if feature_class_field else "").strip()
                if cls.casefold() != "island":
                    continue
                island_rows.append(row)
                if feature_id_field:
                    fid = row.get(feature_id_field, "")
                    if fid in ids:
                        duplicates.add(fid)
                    ids.append(fid)
            parsed.append({
                "source_zip": str(z),
                "text_member": str(txt),
                "delimiter": delimiter,
                "fields": fields,
                "row_count": row_count,
                "island_class_count": len(island_rows),
                "feature_id_field": feature_id_field,
                "name_field": name_field,
                "state_field": state_field,
                "duplicate_feature_ids_within_island_class": sorted(x for x in duplicates if x),
                "island_rows": island_rows,
                "certification_note": "GNIS Island is source taxonomy; rows are named manifestations, not canonical island/cay/islet identities.",
            })
    out = out_dir / "gnis_named_current_island_manifestations.json"
    out.write_text(json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    manifest["named_current"] = {
        "state": "PASS_SOURCE_MANIFESTATIONS_ONLY",
        "manifest_path": str(out),
        "manifest_sha256": sha256_file(out),
        "manifestation_sets": len(parsed),
        "counts": [p["island_class_count"] for p in parsed],
        "zero_duplicate_feature_id_gate": all(not p["duplicate_feature_ids_within_island_class"] for p in parsed),
    }


def freeze_noaa(out_dir: Path, manifest: dict) -> None:
    for family, item_id in NOAA_INPORT_IDS.items():
        url = NOAA_WAF.format(item_id=item_id)
        try:
            frozen = freeze_url(family, url, out_dir / "noaa_ngs", resolved_key=str(item_id))
            manifest["objects"].append(asdict(frozen))
            manifest["discoveries"][family] = {"item_id": item_id, "state": "PASS_METADATA_FROZEN"}
        except Exception as exc:
            manifest["discoveries"][family] = {"item_id": item_id, "state": "BLOCKED", "error": repr(exc)}


def freeze_census(out_dir: Path, manifest: dict) -> None:
    # Freeze directory/index bytes only. Geometry ZIP selection is deferred until
    # index parsing verifies exact 2026 filenames and coverage semantics.
    for family, url in CENSUS_CANDIDATES.items():
        try:
            frozen = freeze_url(family, url, out_dir / "census_tiger")
            manifest["objects"].append(asdict(frozen))
            manifest["discoveries"][family] = {"state": "PASS_INDEX_FROZEN"}
        except Exception as exc:
            manifest["discoveries"][family] = {"state": "BLOCKED", "error": repr(exc)}


def freeze_historical(out_dir: Path, manifest: dict) -> None:
    for family, key in GNIS_HISTORICAL.items():
        url = TNM_BUCKET + "/" + urllib.parse.quote(key, safe="/")
        frozen = freeze_url(family, url, out_dir / "historical", resolved_key=key)
        manifest["objects"].append(asdict(frozen))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="evidence/pr_archipelago/source_snapshots")
    ap.add_argument("--historical", action="store_true")
    args = ap.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "scope": "PR_ARCHIPELAGO_GEOGRAPHY empirical acquisition",
        "generated_utc": utcnow(),
        "objects": [],
        "discoveries": {},
        "named_current": {},
        "certification": {
            "CURRENT_PR_ARCHIPELAGO": "OPEN",
            "HISTORICAL_ARCHIPELAGO_EXHAUSTION": "OPEN",
            "reason": "acquisition alone is not identity/geometry/denominator closure",
        },
    }
    freeze_gnis(out_dir, manifest)
    inspect_domestic_names(out_dir, manifest)
    freeze_noaa(out_dir, manifest)
    freeze_census(out_dir, manifest)
    if args.historical:
        freeze_historical(out_dir, manifest)
    path = out_dir / "source_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "manifest": str(path),
        "sha256": sha256_file(path),
        "named_current": manifest["named_current"],
        "certification": manifest["certification"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
