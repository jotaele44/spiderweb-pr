#!/usr/bin/env python3
"""Build the canonical PR natural-features gazetteer (spiderweb-pr is the owner).

Source of truth is the USGS GNIS ``DomesticNames`` extract, committed compactly as
``data/natural_features/source/gnis_pr_domestic_names.json`` so the build is
reproducible without the 7.8 MB GeoPackage. To refresh from a raw GNIS GeoPackage,
pass ``--gpkg PATH`` (GeoPackage is SQLite; read via stdlib, no geopandas needed).

Emits (under ``data/natural_features/``):
  - pr_natural_features.json      canonical master, one record per feature
  - pr_natural_features.geojson   Point FeatureCollection for the map layer
  - registry/pr_natural_features_manifest.json  provenance + counts + sha256

The record shape is the federation contract in
``schemas/pr_natural_feature.schema.json``. Downstream producers consume domain
slices of this master via ``scripts/build_slices.py``.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "registry" / "natural_features"
SOURCE_JSON = DATA / "source" / "gnis_pr_domestic_names.json"
SCHEMA_VERSION = "pr_natural_feature_v0_1"

# GNIS feature classes that are populated/administrative, not natural features.
EXCLUDE = {"Populated Place", "Civil", "Military", "Census", "Area"}

# feature_type -> group. The group drives per-consumer slices.
GROUP = {
    "river": "hydro", "quebrada": "hydro", "stream": "hydro", "channel": "hydro",
    "canal": "hydro", "lake": "hydro", "reservoir": "hydro", "spring": "hydro",
    "waterfall": "hydro", "basin": "hydro", "gut": "hydro", "wetland": "hydro",
    "mountain": "terrain", "peak": "terrain", "ridge": "terrain",
    "mountain_range": "terrain", "valley": "terrain", "cliff": "terrain",
    "gap": "terrain", "flat": "terrain", "plain": "terrain", "woods": "terrain",
    "cape": "coastal", "bay": "coastal", "beach": "coastal", "bar": "coastal",
    "island": "coastal",
}
# Puerto Rico bounding box (drops off-island GNIS centroid errors).
PR_BOUNDS = (17.7, 18.7, -68.1, -65.1)  # lat_min, lat_max, lon_min, lon_max


def fold(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", fold(s).upper()).strip())


def slug(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", fold(s).lower()).strip("_"))


def _starts(name: str, *prefixes: str) -> bool:
    f = fold(name).lower()
    return any(f.startswith(p) for p in prefixes)


def feature_type(name: str, fclass: str) -> str:
    # GNIS files rivers and quebradas both as Stream, and many quebradas as Valley;
    # the Spanish name prefix is what disambiguates the normalized type.
    if fclass == "Stream":
        if _starts(name, "rio ", "río "):
            return "river"
        if _starts(name, "quebrada "):
            return "quebrada"
        if _starts(name, "cano ", "caño "):
            return "channel"
        if _starts(name, "canal "):
            return "canal"
        return "stream"
    if fclass == "Valley":
        return "quebrada" if _starts(name, "quebrada ") else "valley"
    if fclass == "Summit":
        return "peak" if _starts(name, "pico ") else "mountain"
    mapping = {
        "Reservoir": "reservoir", "Lake": "lake", "Swamp": "wetland",
        "Range": "mountain_range", "Ridge": "ridge", "Cliff": "cliff",
        "Spring": "spring", "Falls": "waterfall", "Bay": "bay", "Cape": "cape",
        "Beach": "beach", "Island": "island", "Channel": "channel", "Canal": "canal",
        "Basin": "basin", "Gut": "gut", "Bar": "bar", "Flat": "flat", "Gap": "gap",
        "Woods": "woods", "Sea": "sea", "Plain": "plain",
    }
    return mapping.get(fclass, slug(fclass))


def load_source_rows(gpkg: Path | None) -> list[dict]:
    """Rows as {gnis_id, gnis_name, feature_class, county, lat, lon}."""
    if gpkg is not None:
        con = sqlite3.connect(str(gpkg))
        rows = con.execute(
            "SELECT feature_id, feature_name, feature_class, county_name, "
            "prim_lat_dec, prim_long_dec FROM DomesticNames "
            "WHERE state_name='Puerto Rico' ORDER BY feature_name, feature_id"
        ).fetchall()
        con.close()
        out = [{"gnis_id": str(r[0]), "gnis_name": r[1], "feature_class": r[2],
                "county": r[3], "lat": r[4], "lon": r[5]} for r in rows]
        SOURCE_JSON.parent.mkdir(parents=True, exist_ok=True)
        SOURCE_JSON.write_text(json.dumps(
            {"_source": "USGS GNIS GeoPackage, DomesticNames, state_name='Puerto Rico'. "
                        "Public domain.", "_count": len(out), "rows": out},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return out
    return json.loads(SOURCE_JSON.read_text(encoding="utf-8"))["rows"]


def build_records(rows: list[dict]) -> list[dict]:
    lat_min, lat_max, lon_min, lon_max = PR_BOUNDS
    prelim = []
    for s in rows:
        fc = s["feature_class"]
        if fc in EXCLUDE:
            continue
        lat, lon = s["lat"], s["lon"]
        if lat is None or lon is None or not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue
        ft = feature_type(s["gnis_name"], fc)
        prelim.append((s, ft, f"place_{ft}_{slug(s['gnis_name'])}"))

    slug_counts = collections.Counter(base for _, _, base in prelim)
    seen: collections.Counter = collections.Counter()
    records = []
    for s, ft, base in prelim:
        cid = base
        if slug_counts[base] > 1:
            seen[base] += 1
            cid = f"{base}_{seen[base]}"
        name = s["gnis_name"]
        aliases = [a for a in dict.fromkeys([name, fold(name)]) if a]
        records.append({
            "canonical_id": cid, "gnis_id": s["gnis_id"], "canonical_name": name,
            "normalized_name": norm_name(name), "feature_type": ft, "group": GROUP[ft],
            "feature_class": fc, "municipality": s["county"],
            "lat": round(s["lat"], 6), "lon": round(s["lon"], 6), "aliases": aliases,
            "source": "USGS GNIS Domestic Names (Puerto Rico)",
        })
    records.sort(key=lambda r: (r["group"], r["feature_type"], r["canonical_name"]))
    return records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpkg", type=Path, default=None,
                    help="Refresh the committed source extract from a GNIS GeoPackage.")
    args = ap.parse_args()

    rows = load_source_rows(args.gpkg)
    records = build_records(rows)
    src_sha = hashlib.sha256(SOURCE_JSON.read_bytes()).hexdigest()
    header = {
        "_schema": SCHEMA_VERSION,
        "_source": "USGS Geographic Names Information System (GNIS) — DomesticNames, "
                   "Puerto Rico. Public domain.",
        "_source_gnis": "source/gnis_pr_domestic_names.json",
        "_source_sha256": src_sha[:16],
        "_count": len(records),
    }
    (DATA / "pr_natural_features.json").write_text(
        json.dumps({**header, "features": records}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": {k: r[k] for k in ("canonical_id", "gnis_id", "canonical_name",
                        "normalized_name", "feature_type", "group", "feature_class",
                        "municipality")}}
        for r in records]}
    (DATA / "pr_natural_features.geojson").write_text(
        json.dumps(geo, ensure_ascii=False), encoding="utf-8")

    by_group = collections.Counter(r["group"] for r in records)
    by_type = collections.Counter(r["feature_type"] for r in records)
    (DATA / "pr_natural_features_manifest.json").write_text(json.dumps({
        "dataset": "pr_natural_features", "version": SCHEMA_VERSION,
        "source": "USGS GNIS DomesticNames (Puerto Rico)", "source_sha256": src_sha,
        "record_count": len(records), "by_group": dict(sorted(by_group.items())),
        "by_feature_type": dict(sorted(by_type.items())),
        "schema": "schemas/pr_natural_feature.schema.json",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"built {len(records)} natural features  groups={dict(sorted(by_group.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
