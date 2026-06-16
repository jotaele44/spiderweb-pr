#!/usr/bin/env python3
"""Populate Spiderweb-PR dataset layers, POI groups, and ILAP types.

Builds normalized GIS dataset layers (``data/gis_layers/*.geojson``, EPSG:4326),
populates ``configs/poi_registry.yaml`` (poi_records grouped by poi_taxonomy),
extends ``configs/lz_registry.yaml`` (known_lz_candidates), and generates
``configs/ilap_registry.yaml`` (observed ILAP type vocabulary + typed nodes).

Sources are the most complete datasets discovered across connected folders
(uploads + PR_Geodata staging). Every emitted feature carries a ``_meta``
provenance block; every layer is registered in
``data/_manifests/gis_layers_manifest.json``.

No demo substitution: only real source records are emitted. Records lacking
usable coordinates are counted and logged, never invented.

Usage:
    python3 scripts/populate_dataset_layers.py            # reads data/sources
    python3 scripts/populate_dataset_layers.py --uploads /extra/dir [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import struct
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from provenance_utils import geojson_feature_meta  # noqa: E402

PRODUCER = "scripts.populate_dataset_layers"
RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

PR_LAT = (17.6, 18.7)
PR_LON = (-68.0, -65.1)

# ── GPKG geometry (WKB) minimal parser ────────────────────────────────────────


def _parse_wkb(buf: bytes, off: int = 0) -> Tuple[Optional[str], Any]:
    little = buf[off] == 1
    end = "<" if little else ">"
    gtype = struct.unpack_from(end + "I", buf, off + 1)[0]
    base = gtype % 1000
    has_z = gtype // 1000 in (1, 3)
    dim = 3 if has_z else 2

    def pts(n: int, o: int) -> Tuple[List[Tuple[float, float]], int]:
        out = []
        for _ in range(n):
            vals = struct.unpack_from(end + "d" * dim, buf, o)
            out.append((vals[0], vals[1]))
            o += 8 * dim
        return out, o

    o = off + 5
    if base == 1:  # Point
        p, _ = pts(1, o)
        return "Point", p[0]
    if base == 2:  # LineString
        n = struct.unpack_from(end + "I", buf, o)[0]
        p, _ = pts(n, o + 4)
        return "LineString", p
    if base == 3:  # Polygon
        nr = struct.unpack_from(end + "I", buf, o)[0]
        o += 4
        rings = []
        for _ in range(nr):
            n = struct.unpack_from(end + "I", buf, o)[0]
            p, o = pts(n, o + 4)
            rings.append(p)
        return "Polygon", rings
    if base in (4, 5, 6, 7):  # Multi*/GeometryCollection → first member
        n = struct.unpack_from(end + "I", buf, o)[0]
        if n == 0:
            return None, None
        return _parse_wkb(buf, o + 4)
    return None, None


def gpkg_geom(blob: Optional[bytes]) -> Tuple[Optional[float], Optional[float], Optional[Dict]]:
    """Return (lon, lat, geojson_geometry) from a GPKG geometry blob."""
    if not blob or len(blob) < 8 or blob[:2] != b"GP":
        return None, None, None
    flags = blob[3]
    env_code = (flags >> 1) & 0x07
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(env_code, 0)
    try:
        gtype, coords = _parse_wkb(blob, 8 + env_len)
    except Exception:
        return None, None, None
    if gtype is None:
        return None, None, None
    if gtype == "Point":
        lon, lat = coords
        return lon, lat, {"type": "Point", "coordinates": [lon, lat]}
    if gtype == "LineString":
        lon, lat = coords[len(coords) // 2]
        return lon, lat, {"type": "LineString", "coordinates": [[x, y] for x, y in coords]}
    if gtype == "Polygon":
        ring = coords[0]
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        return lon, lat, {"type": "Polygon", "coordinates": [[[x, y] for x, y in r] for r in coords]}
    return None, None, None


# ── helpers ───────────────────────────────────────────────────────────────────


def in_pr(lat: Any, lon: Any) -> bool:
    try:
        return PR_LAT[0] <= float(lat) <= PR_LAT[1] and PR_LON[0] <= float(lon) <= PR_LON[1]
    except (TypeError, ValueError):
        return False


def feature(lon: Optional[float], lat: Optional[float], props: Dict, source_artifact: str,
            geometry: Optional[Dict] = None) -> Dict:
    props = {k: v for k, v in props.items()
             if v not in ("", None) and not isinstance(v, (bytes, bytearray))}
    props["_meta"] = geojson_feature_meta(
        producer_module=PRODUCER, source_artifact=source_artifact, produced_at=RUN_TS
    )
    if geometry is None and lon is not None and lat is not None:
        geometry = {"type": "Point", "coordinates": [round(float(lon), 7), round(float(lat), 7)]}
    if geometry is None:
        props["has_coordinates"] = False
    return {"type": "Feature", "geometry": geometry, "properties": props}


class LayerWriter:
    def __init__(self, out_dir: Path, manifest_path: Path):
        self.out_dir = out_dir
        self.manifest_path = manifest_path
        self.entries: List[Dict] = []

    def write(self, name: str, feats: List[Dict], *, source_file: str, source_layer: str,
              domain: str, role: str, crs_note: str = "EPSG:4326",
              skipped_no_coords: int = 0, notes: str = "") -> None:
        path = self.out_dir / f"{name}.geojson"
        fc = {
            "type": "FeatureCollection",
            "meta": {
                "layer_id": name,
                "producer_module": PRODUCER,
                "produced_at": RUN_TS,
                "source_file": source_file,
                "source_layer": source_layer,
                "crs": crs_note,
                "feature_count": len(feats),
                "skipped_no_coords": skipped_no_coords,
                "domain": domain,
                "role": role,
                "notes": notes,
            },
            "features": feats,
        }
        path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        try:
            display_path = str(path.relative_to(REPO_ROOT))
        except ValueError:
            display_path = str(path)
        self.entries.append({
            "layer_id": name, "path": display_path,
            "feature_count": len(feats), "skipped_no_coords": skipped_no_coords,
            "source_file": source_file, "source_layer": source_layer,
            "domain": domain, "role": role, "crs": crs_note, "notes": notes,
        })
        print(f"  layer {name}: {len(feats)} features (skipped {skipped_no_coords})")

    def reference_only(self, name: str, *, source_file: str, source_layer: str,
                       feature_count: int, domain: str, reason: str) -> None:
        self.entries.append({
            "layer_id": name, "path": None, "feature_count": feature_count,
            "source_file": source_file, "source_layer": source_layer,
            "domain": domain, "role": "reference_only", "crs": None, "notes": reason,
        })
        print(f"  ref   {name}: {feature_count} features (reference_only: {reason})")

    def flush(self) -> None:
        manifest = {
            "manifest_id": "gis_layers_manifest",
            "producer_module": PRODUCER,
            "produced_at": RUN_TS,
            "mode": "production",
            "demo_substitution": False,
            "layer_count": len([e for e in self.entries if e["path"]]),
            "reference_only_count": len([e for e in self.entries if not e["path"]]),
            "layers": self.entries,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  manifest → {self.manifest_path}")


def rows_from_gpkg(path: Path, table: str) -> Tuple[List[Dict], List[str]]:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        gcol_row = con.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?", (table,)
        ).fetchone()
        gcol = gcol_row[0] if gcol_row else "geom"
        out = []
        for r in con.execute(f'SELECT * FROM "{table}"'):
            d = dict(r)
            blob = d.pop(gcol, None)
            d["__lon"], d["__lat"], d["__geometry"] = gpkg_geom(blob)
            out.append(d)
        cols = [c for c in out[0].keys() if not c.startswith("__")] if out else []
        return out, cols
    finally:
        con.close()


def find_source(name: str, dirs: List[Path]) -> Optional[Path]:
    for d in dirs:
        p = d / name
        if p.exists():
            try:
                with open(p, "rb") as fh:
                    fh.read(16)
                return p
            except OSError:
                continue
    return None


# ── missing-persons (NamUs) layers ────────────────────────────────────────────
#
# Emits two derived layers from the canonical CSV produced by
# ``scripts/namus_harvest.py``:
#
#   missing_persons_cases       — one Point per redacted case (workbench-internal).
#   missing_persons_by_municipio — one Polygon per municipio with case_count*
#                                  aggregates (federation-eligible).
#
# The case-level layer is intentionally not federation-exported (see Phase 2 of
# the plan); the polygon aggregate is the only future federation surface.

def _ring_contains(point: Tuple[float, float], ring: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-ring test. Stdlib only, exact-on-vertex behavior is
    irrelevant here because we count cases (no boundary tie-breakers)."""
    x, y = point
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_contains(point: Tuple[float, float], geometry: Dict) -> bool:
    """Test point against GeoJSON Polygon or MultiPolygon (outer ring minus holes)."""
    gtype = geometry.get("type")
    if gtype == "Polygon":
        rings = geometry.get("coordinates") or []
        if not rings:
            return False
        outer = [(c[0], c[1]) for c in rings[0]]
        if not _ring_contains(point, outer):
            return False
        for hole in rings[1:]:
            if _ring_contains(point, [(c[0], c[1]) for c in hole]):
                return False
        return True
    if gtype == "MultiPolygon":
        for poly in geometry.get("coordinates") or []:
            if not poly:
                continue
            outer = [(c[0], c[1]) for c in poly[0]]
            if not _ring_contains(point, outer):
                continue
            if any(_ring_contains(point, [(c[0], c[1]) for c in hole]) for hole in poly[1:]):
                continue
            return True
    return False


def _is_iso_date_dirname(name: str) -> bool:
    """True only for a real ISO ``YYYY-MM-DD`` directory name. Guards snapshot
    selection so a non-date sibling ('tmp', '_quarantine', a fat-fingered
    '9999-99-99') can't sort lexicographically above real dates and shadow the
    true latest snapshot. Mirrors namus_harvest._is_iso_date_name."""
    if len(name) != 10 or name[4] != "-" or name[7] != "-":
        return False
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _latest_namus_canonical(sources_root: Path) -> Optional[Path]:
    """Most recent ``<date>/namus_mp_pr_canonical.csv`` under data/sources/namus/."""
    base = sources_root / "namus"
    if not base.exists():
        return None
    snaps = sorted(
        (p for p in base.iterdir() if p.is_dir() and _is_iso_date_dirname(p.name)),
        reverse=True,
    )
    for snap in snaps:
        cand = snap / "namus_mp_pr_canonical.csv"
        if cand.exists():
            return cand
    return None


def emit_missing_persons_layers(
    lw: "LayerWriter",
    *,
    canonical_csv: Path,
    municipios_geojson: Path,
) -> None:
    """Emit the two NamUs-derived layers. Caller owns ``lw.flush()`` timing."""
    if not canonical_csv.exists():
        print(f"  MISSING canonical {canonical_csv} — skipped missing_persons layers")
        return
    if not municipios_geojson.exists():
        print(f"  MISSING {municipios_geojson} — skipped missing_persons_by_municipio")
        return

    with open(canonical_csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    snapshot_date = rows[0]["snapshot_date"] if rows else ""
    redaction_notes = (
        "case_id hashed (12-char SHA-256 prefix); names, photos, DOB, narrative "
        "dropped at harvest (scripts/namus_harvest.py)."
    )

    # ── case-level points ────────────────────────────────────────────────────
    point_feats: List[Dict] = []
    skipped_out_of_pr = 0
    skipped_no_coords = 0
    for r in rows:
        lat_raw, lon_raw = r.get("last_seen_lat"), r.get("last_seen_lon")
        if not lat_raw or not lon_raw:
            skipped_no_coords += 1
            continue
        if not in_pr(lat_raw, lon_raw):
            skipped_out_of_pr += 1
            continue
        props = {k: v for k, v in r.items() if v not in ("", None)}
        point_feats.append(feature(float(lon_raw), float(lat_raw), props, canonical_csv.name))

    lw.write(
        "missing_persons_cases", point_feats,
        source_file=canonical_csv.name, source_layer="csv",
        domain="public_safety", role="primary",
        skipped_no_coords=skipped_no_coords + skipped_out_of_pr,
        notes=(
            f"NamUs PR missing-persons cases, snapshot {snapshot_date}. "
            f"Redaction: {redaction_notes} "
            f"Skipped {skipped_out_of_pr} out-of-PR-bbox rows."
        ),
    )

    # ── aggregated counts by municipio ───────────────────────────────────────
    muni = json.loads(municipios_geojson.read_text(encoding="utf-8"))
    poly_feats: List[Dict] = []
    total_assigned = 0
    for muni_feat in muni.get("features", []):
        geom = muni_feat.get("geometry") or {}
        props_in = muni_feat.get("properties") or {}
        count = active = resolved = cold = 0
        for r in rows:
            lat_raw, lon_raw = r.get("last_seen_lat"), r.get("last_seen_lon")
            if not lat_raw or not lon_raw:
                continue
            try:
                pt = (float(lon_raw), float(lat_raw))
            except (TypeError, ValueError):
                continue
            if not _polygon_contains(pt, geom):
                continue
            count += 1
            status = r.get("status") or ""
            if status == "active":
                active += 1
            elif status in ("resolved_alive", "resolved_deceased"):
                resolved += 1
            elif status == "cold":
                cold += 1
        total_assigned += count
        agg_props = {
            "GEOID": props_in.get("GEOID"),
            "NAME": props_in.get("NAME"),
            "NAMELSAD": props_in.get("NAMELSAD"),
            "case_count": count,
            "case_count_active": active,
            "case_count_resolved": resolved,
            "case_count_cold": cold,
            "snapshot_date": snapshot_date,
            # NOTE: cases_per_100k is intentionally absent in phase 1.
            # ``feature()`` strips None/empty values so a placeholder of None
            # would simply vanish from output (no schema benefit). Phase 2
            # joins a municipio-population layer and writes a real value.
        }
        poly_feats.append(feature(None, None, agg_props, canonical_csv.name, geometry=geom))

    # Conservation check: an in-PR case whose point lands in no municipio polygon
    # (coastal sliver, boundary gap, simplified geometry) is in the cases layer
    # but in zero aggregate polygons. This is the federation-eligible surface, so
    # surface the residual instead of letting the aggregate quietly undercount.
    # max(0, …): a point on a shared municipio boundary can match two polygons
    # and be double-counted, which would otherwise print a negative residual.
    unassigned = max(0, len(point_feats) - total_assigned)
    if unassigned:
        print(f"  WARN missing_persons_by_municipio: {unassigned} in-PR case(s) "
              f"fell in no municipio polygon (not counted in any aggregate)")

    lw.write(
        "missing_persons_by_municipio", poly_feats,
        source_file=canonical_csv.name, source_layer="csv+municipios.geojson",
        domain="public_safety", role="aggregate",
        notes=(
            f"NamUs cases aggregated to {municipios_geojson.name} polygons. "
            f"Zero-case municipios preserved. {total_assigned} of "
            f"{len(point_feats)} in-PR cases assigned; {unassigned} fell in no "
            f"polygon. Redaction: {redaction_notes}"
        ),
    )


# ── main build ────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uploads", type=Path, default=None,
                    help="optional extra source dir (session uploads)")
    ap.add_argument("--staging", type=Path, default=REPO_ROOT / "data" / "sources",
                    help="canonical local source dir (default: data/sources)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    src_dirs = [d for d in (args.uploads, args.staging) if d is not None]

    out_dir = REPO_ROOT / "data" / "gis_layers"
    man_dir = REPO_ROOT / "data" / "_manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)
    lw = LayerWriter(out_dir, man_dir / "gis_layers_manifest.json")

    import yaml  # PyYAML — same dependency config_loader uses

    # ── 1. Consolidated master registry (most complete typed POI source) ──
    cons_path = find_source("Spiderweb_Consolidated_Master_Registry.geojson", src_dirs)
    poi_records: List[Dict] = []
    # Order matters: subcategory-specific rules MUST precede category catch-alls,
    # otherwise e.g. Hydrology swallows its Water Infrastructure / Subsurface rows.
    # mode: "prefix" matches subcategory.startswith, "contains" matches substring.
    group_map = [
        ((None, "Water Infrastructure", "prefix"), "WATER_SEWER"),
        ((None, "Subsurface", "prefix"), "SUBSURFACE_INDICATOR"),
        ((None, "Vieques Contamination", "prefix"), "MILITARY_FEDERAL"),
        ((None, "Airports", "prefix"), "TRANSPORTATION"),
        ((None, "Landing Zones", "prefix"), "TRANSPORTATION"),
        ((None, "Residential Cover", "prefix"), "RESIDENTIAL_COVER"),
        ((None, "Contamination Sites", "prefix"), "INDUSTRIAL"),
        ((None, "Industrial", "contains"), "INDUSTRIAL"),
        ((None, "Protected Areas", "prefix"), "TERRAIN"),
        (("Hydrology", None, None), "HYDRO"),
        (("Power Infrastructure", None, None), "POWER_GRID"),
        (("Industrial", None, None), "INDUSTRIAL"),
        (("Military", None, None), "MILITARY_FEDERAL"),
        (("Signal Detection", None, None), "ANOMALY_LAYER"),
    ]

    def map_group(cat: str, sub: str) -> Optional[str]:
        for (mc, ms, mode), grp in group_map:
            if ms is not None:
                hit = sub.startswith(ms) if mode == "prefix" else (ms in sub)
                if hit and (mc is None or cat == mc):
                    return grp
            elif mc is not None and cat == mc:
                return grp
        return None

    if cons_path:
        d = json.loads(cons_path.read_text(encoding="utf-8"))
        feats, skipped = [], 0
        group_counts: Dict[str, int] = {}
        for f in d.get("features", []):
            p = f.get("properties") or {}
            g = (f.get("geometry") or {}).get("coordinates") or [None, None]
            lon, lat = (g[0], g[1]) if isinstance(g, list) and len(g) >= 2 else (None, None)
            has_xy = in_pr(lat, lon)
            if (lon is not None or lat is not None) and not has_xy:
                skipped += 1  # had coordinates but outside PR envelope → drop
                continue
            if not has_xy:
                lon = lat = None  # keep record, null geometry
            cat, sub = str(p.get("category") or ""), str(p.get("subcategory") or "")
            grp = map_group(cat, sub)
            props = {
                "registry_id": p.get("consolidated_id") or p.get("record_id"),
                "name": p.get("name"), "category": cat, "subcategory": sub,
                "poi_group": grp, "confidence": p.get("confidence"),
                "source_dataset": p.get("data_source") or p.get("source_layer"),
                "source_package": p.get("source_package"),
            }
            feats.append(feature(lon, lat, props, cons_path.name))
            if grp:
                conf = p.get("confidence")
                try:
                    confv = float(conf) if conf is not None else None
                except (TypeError, ValueError):
                    confv = None
                tier = "T2" if (confv or 0) >= 0.8 else "T3"
                poi_records.append({
                    "poi_id": str(props["registry_id"] or f"poi_{len(poi_records):05d}"),
                    "canonical_name": str(props["name"] or "")[:160] or None,
                    "poi_class": grp,
                    "source_subcategory": sub or None,
                    "lat": round(float(lat), 6) if lat is not None else None,
                    "lon": round(float(lon), 6) if lon is not None else None,
                    "has_coordinates": lat is not None,
                    "confidence": confv,
                    "visibility": "V3", "evidence_tier": tier, "status": "registered",
                    "source_dataset": props["source_dataset"],
                    "source_file": cons_path.name,
                })
                group_counts[grp] = group_counts.get(grp, 0) + 1
        lw.write("consolidated_master_registry", feats, source_file=cons_path.name,
                 source_layer="features", domain="poi", role="primary",
                 skipped_no_coords=skipped,
                 notes="Most complete typed POI source (supersedes Spiderweb_POI_Master).")
        print("  poi_records groups:", dict(sorted(group_counts.items())))

    # ── 2. Hydro layers ──
    hp = find_source("PR_Hydro_Layer_100pct_Normalized_Points.csv", src_dirs)
    if hp:
        feats, skipped = [], 0
        with open(hp, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if not in_pr(r.get("lat"), r.get("lon")):
                    skipped += 1
                    continue
                feats.append(feature(float(r["lon"]), float(r["lat"]), {
                    "name": r.get("name_norm") or r.get("name"),
                    "hydro_type": r.get("hydro_type"), "class_norm": r.get("class_norm"),
                    "feature_class_raw": r.get("feature_class_raw"),
                    "source_dataset": r.get("source_file"),
                }, hp.name))
        lw.write("hydro_points_normalized", feats, source_file=hp.name, source_layer="csv",
                 domain="hydro", role="primary", skipped_no_coords=skipped,
                 notes="100pct normalized hydro point layer (most complete hydro source).")

    hm = find_source("Spiderweb_Hydro_Master_v3.gpkg", src_dirs)
    if hm:
        rows, _ = rows_from_gpkg(hm, "Spiderweb_Hydro_Master_v3")
        feats, skipped = [], 0
        for r in rows:
            if r["__lon"] is None or not in_pr(r["__lat"], r["__lon"]):
                skipped += 1
                continue
            props = {k: v for k, v in r.items() if not k.startswith("__") and k != "fid"}
            feats.append(feature(r["__lon"], r["__lat"], props, hm.name, geometry=r["__geometry"]))
        lw.write("hydro_master_v3", feats, source_file=hm.name,
                 source_layer="Spiderweb_Hydro_Master_v3", domain="hydro", role="primary",
                 skipped_no_coords=skipped)

    # ── 3. Spiderweb hydro graph (nodes/edges v5) + karst subsurface v2 ──
    nodes_csv = find_source("pr_spiderweb_nodes_v5.csv", src_dirs)
    node_xy: Dict[str, Tuple[float, float]] = {}
    if nodes_csv:
        feats, skipped = [], 0
        with open(nodes_csv, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if not (r.get("node_id") or "").strip():
                    skipped += 1  # blank row in source
                    continue
                lat, lon = r.get("lat_dd"), r.get("lon_dd")
                if in_pr(lat, lon):
                    node_xy[r["node_id"]] = (float(lon), float(lat))
                    lon_f, lat_f = float(lon), float(lat)
                else:
                    lon_f = lat_f = None  # source gap — keep record, null geometry
                feats.append(feature(lon_f, lat_f, {
                    "node_id": r.get("node_id"), "name": r.get("name"),
                    "node_type": r.get("node_type"), "basin": r.get("basin"),
                    "sub_corridor": r.get("sub_corridor"), "aquifer_unit": r.get("aquifer_unit"),
                    "flow_role": r.get("flow_role"), "ilap_score": r.get("ilap_score"),
                }, nodes_csv.name))
        no_xy = sum(1 for f in feats if f["geometry"] is None)
        lw.write("spiderweb_graph_nodes_v5", feats, source_file=nodes_csv.name, source_layer="csv",
                 domain="hydro_graph", role="primary", skipped_no_coords=skipped,
                 notes=f"{no_xy} nodes carry no coordinates in source (null geometry, "
                       "has_coordinates=false); matches null geom rows in PR_Karst_Subsurface_v2.")

    edges_csv = find_source("pr_spiderweb_edges_v5.csv", src_dirs)
    # NOTE: do NOT also require node_xy — when the nodes CSV is missing/empty the
    # per-edge `a and b` check below already writes null geometry with attributes
    # preserved. Gating on node_xy silently dropped the entire edges layer.
    if not edges_csv:
        print("  MISSING source pr_spiderweb_edges_v5.csv — skipped spiderweb_graph_edges_v5")
    else:
        feats, skipped = [], 0
        unresolved = 0
        with open(edges_csv, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if not (r.get("edge_id") or "").strip():
                    skipped += 1
                    continue
                a, b = node_xy.get(r.get("from_node", "")), node_xy.get(r.get("to_node", ""))
                geom = ({"type": "LineString", "coordinates": [[a[0], a[1]], [b[0], b[1]]]}
                        if a and b else None)
                if geom is None:
                    unresolved += 1
                feats.append(feature(None, None, {
                    "edge_id": r.get("edge_id"), "name": r.get("name"),
                    "edge_type": r.get("edge_type"), "from_node": r.get("from_node"),
                    "to_node": r.get("to_node"), "directionality": r.get("directionality"),
                    "confidence": r.get("confidence_0_1"), "length_m": r.get("length_m"),
                    "ilap_score": r.get("ilap_score"), "covert_flags": r.get("covert_flags"),
                }, edges_csv.name, geometry=geom))
        lw.write("spiderweb_graph_edges_v5", feats, source_file=edges_csv.name, source_layer="csv",
                 domain="hydro_graph", role="primary", skipped_no_coords=skipped,
                 notes="Straight-line edge geometry from node endpoints (schematic, not "
                       f"hydrographic); {unresolved} edges unresolved (an endpoint lacks "
                       "coordinates in source) → null geometry, attributes preserved.")

    karst = find_source("PR_Karst_Subsurface_v2.gpkg", src_dirs)
    if karst:
        for tbl, lname in (("pr_subsurface_nodes", "karst_subsurface_nodes_v2"),
                           ("pr_subsurface_edges", "karst_subsurface_edges_v2")):
            rows, _ = rows_from_gpkg(karst, tbl)
            feats = []
            null_geom = 0
            for r in rows:
                if r["__lon"] is None:
                    null_geom += 1  # null geometry in source — keep attributes
                props = {k: v for k, v in r.items() if not k.startswith("__") and k != "fid"}
                feats.append(feature(r["__lon"], r["__lat"], props, karst.name, geometry=r["__geometry"]))
            lw.write(lname, feats, source_file=karst.name, source_layer=tbl,
                     domain="subsurface", role="primary", skipped_no_coords=0,
                     notes=f"{null_geom} rows have null geometry in the source GPKG "
                           "(attributes preserved, has_coordinates=false).")

    # ── 4. GPKG point/facility layers ──
    gpkg_specs = [
        ("PR_Landing_Zones_Master.gpkg", "all_landing_zones", "landing_zones_master", "lz"),
        ("Military & Aviation.gpkg", "military_aviation", "military_aviation", "military"),
        ("PR_Industrial_AllTypes_Master.gpkg", "industrial_master", "industrial_master", "industrial"),
        ("NID_v1_-639595725017535442.gpkg", "Dams", "nid_dams", "hydro"),
        ("PRI.gpkg", "power_plant", "pri_power_plants", "power"),
        ("PRI.gpkg", "power_substation_polygon", "pri_substations", "power"),
        ("PRI.gpkg", "power_line", "pri_power_lines", "power"),
        ("PRI.gpkg", "wastewater_plant", "pri_wastewater_plants", "water_sewer"),
        ("PRI.gpkg", "water_treatment_plant", "pri_water_treatment_plants", "water_sewer"),
        ("PRI.gpkg", "pumping_station", "pri_pumping_stations", "water_sewer"),
        ("PRI.gpkg", "water_reservoir", "pri_water_reservoirs", "hydro"),
        ("PRI.gpkg", "mast", "pri_masts", "utility"),
    ]
    lz_rows: List[Dict] = []
    lz_status: Dict[Any, str] = {}
    lz_src = find_source("PR_Landing_Zones_Master.gpkg", src_dirs)
    if lz_src:
        for tbl, status in (("active_verified", "active_verified"),
                            ("historic_inactive", "historic_inactive"),
                            ("candidates", "candidate")):
            try:
                rws, _ = rows_from_gpkg(lz_src, tbl)
                for r in rws:
                    key = r.get("name") or r.get("Name") or r.get("fid")
                    lz_status[key] = status
            except Exception as exc:
                # Visible, not silent: a swallowed read error here leaves
                # lz_status empty, so verified/historic LZs get silently demoted
                # to T3 'candidate' in lz_registry.yaml.
                print(f"  ERROR reading {lz_src.name}:{tbl}: {exc} "
                      f"— LZs from this table left unclassified")

    for fname, tbl, lname, domain in gpkg_specs:
        src = find_source(fname, src_dirs)
        if not src:
            print(f"  MISSING source {fname} — skipped {lname}")
            continue
        try:
            rows, _ = rows_from_gpkg(src, tbl)
        except Exception as exc:
            print(f"  ERROR reading {fname}:{tbl}: {exc}")
            continue
        feats, skipped = [], 0
        for r in rows:
            if r["__lon"] is None or not in_pr(r["__lat"], r["__lon"]):
                skipped += 1
                continue
            props = {k: v for k, v in r.items() if not k.startswith("__") and k != "fid"}
            geom = r["__geometry"]
            if lname == "pri_substations" and geom and geom["type"] == "Polygon":
                geom = None  # store centroid point; footprint kept in source GPKG
                props["geometry_simplified"] = "polygon_centroid"
            if lname == "landing_zones_master":
                key = props.get("name") or props.get("Name")
                props["lz_status"] = lz_status.get(key, "unspecified")
                lz_rows.append(dict(props, __lat=r["__lat"], __lon=r["__lon"]))
            feats.append(feature(r["__lon"], r["__lat"], props, src.name, geometry=geom))
        lw.write(lname, feats, source_file=src.name, source_layer=tbl, domain=domain,
                 role="primary", skipped_no_coords=skipped)

    # ── 5. ILAP layers + vocabulary ──
    ilap_sources: Dict[str, Dict] = {}

    im = find_source("Spiderweb_ILAP_Master.geojson", src_dirs)
    placeholder_count = 0
    if im:
        d = json.loads(im.read_text(encoding="utf-8"))
        feats, skipped = [], 0
        subcats: Dict[str, int] = {}
        for f in d.get("features", []):
            p = f.get("properties") or {}
            g = (f.get("geometry") or {}).get("coordinates") or [None, None]
            if not in_pr(g[1], g[0]):
                skipped += 1
                continue
            notes = str(p.get("notes") or "")
            placeholder = "PLACEHOLDER" in notes.upper()
            placeholder_count += placeholder
            subcats[p.get("subcategory") or "?"] = subcats.get(p.get("subcategory") or "?", 0) + 1
            feats.append(feature(g[0], g[1], {
                "ilap_id": p.get("ilap_id"), "name": p.get("name"),
                "ilap_subcategory": p.get("subcategory"), "confidence": p.get("confidence"),
                "coordinate_quality": p.get("coordinate_quality"),
                "coordinate_placeholder": placeholder,
                "source_dataset": p.get("source_dataset"),
            }, im.name))
        lw.write("ilap_master_nodes", feats, source_file=im.name, source_layer="features",
                 domain="ilap", role="primary", skipped_no_coords=skipped,
                 notes=f"{placeholder_count} features sit on municipality-centroid placeholder "
                       "coordinates (coordinate_placeholder=true); do not treat as precise.")
        ilap_sources["Spiderweb_ILAP_Master.geojson:subcategory"] = subcats

    for fname, lname in (("Spiderweb_ILAP_Predictions.geojson", "ilap_predictions"),
                         ("Spiderweb_Hydro_Candidate_Nodes.geojson", "hydro_candidate_nodes"),
                         ("Spiderweb_Water_Signals.geojson", "water_signals"),
                         ("AASB_All_Corridors_Nodes_v1.geojson", "aasb_corridor_nodes"),
                         ("geojson__Spiderweb_Corridors_Master.geojson", "subsurface_corridors_master"),
                         ("Spiderweb_Corridor_Index_v1.geojson", "corridor_index_v1"),
                         ("Fire_Stations_Spiderweb_Master_Consolidated.geojson", "fire_stations_consolidated"),
                         ("FIC_OSAP_Final_Set_v3.geojson", "fic_osap_final_set_v3"),
                         ("FIC_OSAP_Candidates_v2.geojson", "fic_osap_candidates_v2"),
                         ("FIC_OSAP_ILAP_Links_v4.geojson", "fic_osap_ilap_links_v4"),
                         ("FIC_OSAP_ILAP_Paths_v6_All.geojson", "fic_osap_ilap_paths_v6")):
        src = find_source(fname, src_dirs)
        if not src:
            print(f"  MISSING source {fname} — skipped {lname}")
            continue
        d = json.loads(src.read_text(encoding="utf-8"))
        feats, skipped = [], 0
        vocab: Dict[str, int] = {}
        for f in d.get("features", []):
            p = dict(f.get("properties") or {})
            geom = f.get("geometry")
            if not geom:
                skipped += 1
                continue
            if geom.get("type") == "Point":
                coords = geom.get("coordinates") or []
                if len(coords) < 2:
                    skipped += 1  # malformed point (was an uncaught unpack error)
                    continue
                lon, lat = coords[0], coords[1]
                if lname.startswith("fic_osap"):
                    pass  # offshore layers legitimately fall outside the land bbox
                elif not in_pr(lat, lon):
                    skipped += 1
                    continue
                # Normalize to 2D so a 3D [lon,lat,z] source point doesn't carry
                # its Z into output (the rest of the pipeline emits [lon,lat]).
                geom = {"type": "Point", "coordinates": [lon, lat]}
            else:
                try:
                    c = geom["coordinates"]
                    while isinstance(c[0], (list, tuple)):
                        c = c[0]
                    lon, lat = c[:2]
                except Exception:
                    skipped += 1
                    continue
            for tk in ("ilap_type", "ilap_class", "type", "posture", "link_type"):
                if p.get(tk):
                    vocab[f"{tk}={p[tk]}"] = vocab.get(f"{tk}={p[tk]}", 0) + 1
            feats.append(feature(lon, lat, p, src.name, geometry=geom))
        role = "primary"
        lw.write(lname, feats, source_file=src.name, source_layer="features",
                 domain="ilap" if "ilap" in lname or lname.startswith("aasb") else "support",
                 role=role, skipped_no_coords=skipped)
        if vocab:
            ilap_sources[src.name] = vocab

    # ── 6. CSV support layers ──
    csv_specs = [
        ("PR_WaterWorks_MasterDataset_v1.csv", "waterworks_master_v1", "water_sewer",
         "Latitude", "Longitude"),
        ("Spiderweb_Verified_Batch1_to_4_with_Resolved.csv", "verified_coordinates_overlay",
         "verification", "lat_verified", "lon_verified"),
    ]
    for fname, lname, domain, latk, lonk in csv_specs:
        src = find_source(fname, src_dirs)
        if not src:
            print(f"  MISSING source {fname} — skipped {lname}")
            continue
        feats, skipped = [], 0
        with open(src, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if not in_pr(r.get(latk), r.get(lonk)):
                    skipped += 1
                    continue
                props = {k: v for k, v in r.items() if k not in (latk, lonk)}
                feats.append(feature(float(r[lonk]), float(r[latk]), props, src.name))
        lw.write(lname, feats, source_file=src.name, source_layer="csv", domain=domain,
                 role="overlay" if lname == "verified_coordinates_overlay" else "primary",
                 skipped_no_coords=skipped)

    # ── 7. Reference-only registrations (too heavy / unresolved CRS / superseded) ──
    # Registered below by literal name; no live GPKG inspection is needed. A
    # prior dead `gpkg_contents` probe here looped with a `pass` body (produced
    # nothing) yet ran an unguarded query that raised an uncaught
    # OperationalError on a present-but-non-GPKG file — aborting the entire run
    # AFTER all layer building but BEFORE any manifest/registry was written, and
    # leaking the connection. Removed.
    for name, sf, sl, cnt, dom, why in [
        ("prepa_transmission_lines_2014", "Spiderweb_Master_Warehouse_EXEC_20260217.gpkg",
         "05_ENERGY__PREPA2014__g37_electric_LineasTransmision_2014", 13539, "power",
         "Authoritative 2014 PREPA corridors; kept in source GPKG (size). Promote on demand."),
        ("prepa_transmission_structures_2014", "Spiderweb_Master_Warehouse_EXEC_20260217.gpkg",
         "05_ENERGY__PREPA2014__g37_electric_EstructurasTransmision_2014", 38306, "power",
         "38k tower points; line layer carries corridor signal."),
        ("wetlands_nwi_prvi", "Spiderweb_Master_Warehouse_EXEC_20260217.gpkg",
         "02_HYDROLOGY_KARST__Wetlands_NWI_PRVI", 18272, "hydro",
         "Non-EPSG:4326 srs_id=100000; needs reprojection before promotion."),
        ("pri_power_towers", "PRI.gpkg", "power_tower", 22778, "power",
         "Dense tower points; superseded by line + substation layers for scoring."),
        ("pri_power_generator_polygons", "PRI.gpkg", "power_generator_polygon", 21488, "power",
         "Rooftop-generator polygons; not operationally relevant at registry tier."),
        ("gazetteer_pr_domestic_names", "Gazetteer_PR_GPKG.gpkg", "DomesticNames", 5818, "reference",
         "USGS GNIS names; srs_id=100000 container — use for alias resolution, not geometry."),
        ("ilap_dem_anomalies", "Data/ILAP_Pipeline/outputs/ILAP_anomalies.gpkg",
         "ILAP_anomalies", 433443, "ilap",
         "Raw DEM anomaly polygons (433k); pipeline output, consumed by PR-DEM tools directly."),
        ("public_schools_all", "geojson__PR_Public_Schools_ALL.geojson", "features", 1686,
         "reference", "Already represented inside consolidated_master_registry (Education)."),
    ]:
        lw.reference_only(name, source_file=sf, source_layer=sl, feature_count=cnt,
                          domain=dom, reason=why)

    # ── 7b. Missing persons (NamUs) — case-level points + municipio aggregate ──
    namus_canonical = _latest_namus_canonical(REPO_ROOT / "data" / "sources")
    if namus_canonical is not None:
        emit_missing_persons_layers(
            lw,
            canonical_csv=namus_canonical,
            municipios_geojson=REPO_ROOT / "data" / "municipios.geojson",
        )
    else:
        print("  MISSING data/sources/namus/<date>/namus_mp_pr_canonical.csv "
              "— skipped missing_persons layers (run scripts/namus_harvest.py first)")

    lw.flush()

    # ── 8. configs/poi_registry.yaml ──
    poi_reg_path = REPO_ROOT / "configs" / "poi_registry.yaml"
    reg = yaml.safe_load(poi_reg_path.read_text(encoding="utf-8"))
    reg["version"] = "rlsm_poi_registry_v0_2"
    reg["populated_at"] = RUN_TS
    reg["population_source"] = {
        "primary": "Spiderweb_Consolidated_Master_Registry.geojson",
        "producer": PRODUCER,
        "group_mapping_note": (
            "category/subcategory → poi_taxonomy mapping: Hydrology→HYDRO; Power "
            "Infrastructure→POWER_GRID; Water Infrastructure*→WATER_SEWER; *Industrial* & "
            "Contamination Sites→INDUSTRIAL; Airports & Landing Zones→TRANSPORTATION; "
            "Military & Vieques Contamination*→MILITARY_FEDERAL; Subsurface*→"
            "SUBSURFACE_INDICATOR; Signal Detection→ANOMALY_LAYER (Residential Cover→"
            "RESIDENTIAL_COVER); Protected Areas→TERRAIN. Education/Recreation/Health/"
            "Emergency Services intentionally excluded from poi_records (reference layers; "
            "see data/gis_layers/consolidated_master_registry.geojson)."
        ),
    }
    reg["poi_records"] = poi_records
    if not args.dry_run:
        poi_reg_path.write_text(
            yaml.safe_dump(reg, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8")
    print(f"  poi_registry: {len(poi_records)} poi_records")

    # ── 9. configs/lz_registry.yaml ──
    lz_reg_path = REPO_ROOT / "configs" / "lz_registry.yaml"
    lzreg = yaml.safe_load(lz_reg_path.read_text(encoding="utf-8"))
    existing = {e.get("canonical_name") for e in lzreg.get("known_lz_candidates", [])}
    kw_map = [
        ("helipad", "FORMAL_HELIPAD"), ("heliport", "FORMAL_HELIPAD"),
        ("hospital", "HOSPITAL_LZ"), ("medical", "HOSPITAL_LZ"), ("medevac", "HOSPITAL_LZ"),
        ("prepa", "UTILITY_LZ"), ("luma", "UTILITY_LZ"), ("substation", "UTILITY_LZ"),
        ("plant", "INDUSTRIAL_LZ"), ("refinery", "INDUSTRIAL_LZ"), ("port", "INDUSTRIAL_LZ"),
        ("dam", "RESERVOIR_LZ"), ("reservoir", "RESERVOIR_LZ"), ("embalse", "RESERVOIR_LZ"),
        ("beach", "COASTAL_LZ"), ("coast", "COASTAL_LZ"), ("marina", "COASTAL_LZ"),
        ("roof", "ROOFTOP_LZ"), ("field", "FIELD_LZ"), ("road", "ROAD_LZ"),
    ]
    added = 0
    for r in lz_rows:
        name = str(r.get("name") or r.get("Name") or "").strip()
        if not name or name in existing:
            continue
        low = name.lower()
        lz_class = next((c for k, c in kw_map if k in low), "IMPROVISED_LZ")
        status_src = r.get("lz_status", "unspecified")
        rec = {
            "lz_id": "lz_" + "".join(ch if ch.isalnum() else "_" for ch in low)[:48].strip("_"),
            "canonical_name": name,
            "lz_class": lz_class,
            "lz_class_method": "keyword_inference_from_name",
            "lat": round(float(r["__lat"]), 6), "lon": round(float(r["__lon"]), 6),
            "visibility": "V3",
            "evidence_tier": "T2" if status_src == "active_verified" else "T3",
            "status": {"active_verified": "verified_active",
                       "historic_inactive": "historic",
                       "candidate": "candidate"}.get(status_src, "candidate"),
            "source_file": "PR_Landing_Zones_Master.gpkg",
            "source_layer_status": status_src,
        }
        for extra in ("municipality", "municipio", "type", "notes", "surface"):
            if r.get(extra):
                rec[extra] = r[extra]
        lzreg["known_lz_candidates"].append(rec)
        added += 1
    lzreg["version"] = "rlsm_lz_registry_v0_2"
    lzreg["populated_at"] = RUN_TS
    if not args.dry_run:
        lz_reg_path.write_text(
            yaml.safe_dump(lzreg, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8")
    print(f"  lz_registry: +{added} records (existing {len(existing)} kept)")

    # ── 10. configs/ilap_registry.yaml (new) ──
    ilap_nodes: List[Dict] = []
    v14 = find_source("Spiderweb_Consolidated_Dataset_v1_4.sqlite", src_dirs)
    matrix_types: Dict[str, int] = {}
    if v14:
        con = sqlite3.connect(str(v14))
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT * FROM hydro_ilap_matrix"):
            d = dict(r)
            t = d.get("ilap_type_calc")
            matrix_types[t] = matrix_types.get(t, 0) + 1
            lat, lon = d.get("lat_filled"), d.get("lon_filled")
            ilap_nodes.append({
                "node_id": d.get("registry_id"),
                "name": d.get("name"),
                "ilap_type": t,
                "lat": round(float(lat), 6) if lat is not None else None,
                "lon": round(float(lon), 6) if lon is not None else None,
                "hydro_region_band": d.get("hydro_region_band"),
                "corridor_id": d.get("corridor_id"),
                "corridor_tier": d.get("corridor_tier_calc"),
                "coord_method": d.get("coord_method"),
                "match_confidence": d.get("match_confidence"),
                "visibility": "V3", "status": "registered",
                "source_file": v14.name, "source_table": "hydro_ilap_matrix",
            })
        con.close()
        ilap_sources[f"{v14.name}:hydro_ilap_matrix.ilap_type_calc"] = matrix_types

    aasb = find_source("AASB_All_Corridors_Nodes_v1.geojson", src_dirs)
    if aasb:
        d = json.loads(aasb.read_text(encoding="utf-8"))
        for f in d.get("features", []):
            p = f.get("properties") or {}
            g = (f.get("geometry") or {}).get("coordinates") or [None, None]
            ilap_nodes.append({
                "node_id": p.get("node_id"),
                "name": p.get("poi_name"),
                "ilap_type": p.get("ilap_type"),
                "ilap_subtype": p.get("subtype"),
                "lat": round(float(g[1]), 6) if g[1] is not None else None,
                "lon": round(float(g[0]), 6) if g[0] is not None else None,
                "corridor_id": p.get("corridor_id"),
                "corridor_name": p.get("corridor_name"),
                "municipality": p.get("municipio"),
                "node_confidence": p.get("node_confidence"),
                "structural_role": p.get("structural_role"),
                "visibility": "V3", "status": "registered",
                "source_file": aasb.name, "source_table": "features",
            })

    hydro_graph_types: Dict[str, int] = {}
    if nodes_csv:
        with open(nodes_csv, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                t = r.get("node_type") or "unspecified"
                hydro_graph_types[t] = hydro_graph_types.get(t, 0) + 1
        ilap_sources[f"{nodes_csv.name}:node_type"] = hydro_graph_types

    canonical_groups = {
        "HYDRO": ["Hydro", "ILAP-Hydro-Karst", "Dam Nodes", "Dam-Adjacent ILAP Candidate",
                  "Dam", "Reservoir", "Hydroelectric Plant", "River", "Lagoon", "Canal",
                  "Spring", "Losing Stream"],
        "COASTAL": ["Coastal Outlet", "Coastal", "ILAP-Coastal"],
        "UTILITY": ["Utility"],
        "URBAN": ["ILAP-Urban"],
        "RIDGE_TERRAIN": ["Ridge", "ILAP-Ridge"],
        "INDUSTRIAL": ["Industrial", "Industrial-River ILAP Candidate", "Quarry"],
        "SUBSURFACE": ["Subsurface Entry Nodes", "Sinkhole", "Karst Infiltration Zone",
                       "Swallow Hole", "Subsurface_Karst"],
        "SUBSEA": ["logistics", "stealth"],
        "UNSPECIFIED": ["ILAP Nodes", "unspecified"],
    }

    ilap_reg = {
        "version": "ilap_registry_v0_1",
        "generated_at": RUN_TS,
        "producer_module": PRODUCER,
        "canonical_definition": (
            "ILAP = infrastructure_linked_access_point (configs/spiderweb_terms.yaml). "
            "Types below are observed vocabulary from source datasets — values are "
            "preserved verbatim per location_naming_guardrails (never invented)."
        ),
        "ilap_type_sources": {k: dict(sorted(v.items(), key=lambda x: -x[1]))
                              for k, v in ilap_sources.items()},
        "ilap_type_canonical_groups": canonical_groups,
        "corridor_type_enum_note": (
            "Distinct from schemas/ilap_corridor_candidate.schema.json corridor_type "
            "(point_to_point|patrol|survey|hub_spoke|unknown), which classifies flight "
            "corridors, not ILAP ground nodes."
        ),
        "ilap_nodes": ilap_nodes,
    }
    ilap_path = REPO_ROOT / "configs" / "ilap_registry.yaml"
    if not args.dry_run:
        ilap_path.write_text(
            yaml.safe_dump(ilap_reg, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8")
    print(f"  ilap_registry: {len(ilap_nodes)} nodes, "
          f"{sum(len(v) for v in ilap_sources.values())} observed type values")

    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
