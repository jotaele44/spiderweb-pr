#!/usr/bin/env python3
"""
Spiderweb PR Road Gazetteer Ingest

Purpose:
  Build canonical road-name gazetteer outputs from authoritative or supporting road sources:
  - DTOP / ACT route data (T1, if supplied locally)
  - Census TIGER/Line county roads (T2)
  - OSM Geofabrik Puerto Rico roads (T3)

Boundary:
  This script only emits road:* namespace features. It does not duplicate GNIS non-road features.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

try:
    import geopandas as gpd
except Exception:  # pragma: no cover
    gpd = None

ROUTE_PATTERNS = [
    re.compile(r"\b(?:PR|P\.?R\.?|PRI|P\.R|PUERTO\s+RICO\s+(?:HIGHWAY|HWY|ROUTE)|CARRETERA(?:\s+ESTATAL)?|CARR\.?|RUTA)\s*[- ]?\s*(\d{1,5}[A-Z]?)\b", re.I),
    re.compile(r"\b(\d{1,5}[A-Z]?)\s*(?:PR|P\.?R\.?)\b", re.I),
]

MFTCC_VEHICLE_CLASSES = {"S1100", "S1200", "S1400", "S1500", "S1630", "S1640"}

STREET_GENERIC = {
    "CALLE", "AVE", "AVENIDA", "BLVD", "BOULEVARD", "CAMINO", "CARRETERA", "CARR", "CT", "DR", "HIGHWAY", "HWY",
    "PASEO", "PZA", "PLAZA", "RAMAL", "RD", "ROAD", "RUTA", "ST", "TRAIL", "VIA"
}

def strip_diacritics(value: str) -> str:
    if value is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c))

def normalize_name(value: str) -> str:
    s = strip_diacritics(value or "").upper().strip()
    s = re.sub(r"[.,;:()\[\]{}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\bP\s*R\b", "PR", s)
    s = re.sub(r"\bPUERTO RICO HIGHWAY\b", "PR", s)
    s = re.sub(r"\bPUERTO RICO HWY\b", "PR", s)
    s = re.sub(r"\bCARRETERA ESTATAL\b", "CARRETERA", s)
    s = re.sub(r"\bCARR\b", "CARRETERA", s)
    s = re.sub(r"\bRTE\b", "RUTA", s)
    s = re.sub(r"\bPR\s*[- ]\s*(\d{1,5}[A-Z]?)\b", r"PR-\1", s)
    return s

def route_number_from_text(*values: object) -> str:
    text = " ".join(str(v) for v in values if v is not None and str(v).strip() and str(v).lower() != "nan")
    if not text:
        return ""
    for pat in ROUTE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).upper()
    return ""

def make_road_id(source_family: str, source_record_id: str, route_number: str = "", normalized_name: str = "") -> str:
    base = f"{source_family}|{source_record_id}|{route_number}|{normalized_name}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    fam = source_family.lower().replace("_roads", "").replace("_route_data", "").replace("_", "-")
    return f"road:{fam}:{digest}"

def alias_variants(route_number: str, canonical_name: str = "") -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    seen = set()
    def add(name: str, typ: str) -> None:
        n = str(name or "").strip()
        key = strip_diacritics(n).upper().strip()
        if n and key not in seen:
            seen.add(key)
            out.append((n, typ))
    add(canonical_name, "canonical")
    if route_number:
        rn = route_number.upper()
        for name in [f"PR-{rn}", f"PR {rn}", f"Puerto Rico Highway {rn}", f"Puerto Rico Route {rn}", f"Carretera PR-{rn}", f"Carretera {rn}", f"Ruta {rn}"]:
            add(name, "generated_variant")
    return out

def safe_wkt(geom) -> str:
    try:
        if geom is None or geom.is_empty:
            return ""
        return geom.wkt
    except Exception:
        return ""

@dataclass
class SourceRead:
    source_id: str
    source_family: str
    source_rank: str
    path_or_url: str
    present_locally: bool
    status: str
    rows_read: int
    notes: str = ""

class RoadGazetteerIngest:
    def __init__(self, source_root: Path, gnis_dir: Path, output_dir: Path, include_nonvehicular: bool = False):
        self.source_root = source_root
        self.gnis_dir = gnis_dir
        self.output_dir = output_dir
        self.include_nonvehicular = include_nonvehicular
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.gov = self._load_gov_units()
        self.source_manifest: List[SourceRead] = []
        self.canonical_rows: List[Dict] = []
        self.name_rows: List[Dict] = []
        self.edge_rows: List[Dict] = []
        self.conflict_rows: List[Dict] = []
        self.now = datetime.now(timezone.utc).isoformat()

    def _load_gov_units(self) -> pd.DataFrame:
        p = self.gnis_dir / "government_units.csv"
        if p.exists():
            df = pd.read_csv(p)
            df = df[df.get("unit_type", "").eq("COUNTY")].copy()
            if "county_numeric" in df.columns:
                df["municipio_geoid"] = df["county_numeric"].apply(lambda x: f"72{int(float(x)):03d}" if pd.notna(x) else "")
            return df
        return pd.DataFrame()

    def run(self) -> None:
        self.ingest_dtop_sources()
        self.ingest_tiger_sources()
        self.ingest_osm_sources()
        self.detect_conflicts()
        self.write_outputs()

    def ingest_dtop_sources(self) -> None:
        dtop_dir = self.source_root / "dtop"
        files = []
        if dtop_dir.exists():
            for ext in ("*.gpkg", "*.shp", "*.geojson", "*.json", "*.csv"):
                files.extend(dtop_dir.glob(ext))
        if not files:
            self.source_manifest.append(SourceRead("DTOP_ROUTE_DATA", "DTOP_ROUTE_DATA", "T1", str(dtop_dir), False, "missing", 0, "No DTOP/ACT route source found."))
            return
        colmap = {}
        cm = dtop_dir / "dtop_column_map.json"
        if cm.exists():
            colmap = json.loads(cm.read_text(encoding="utf-8"))
        for path in files:
            self._read_generic_road_file(path, "DTOP_ROUTE_DATA", "T1", f"DTOP_ROUTE_DATA_{path.stem}", colmap)

    def ingest_tiger_sources(self) -> None:
        tiger_dir = self.source_root / "tiger2025"
        zips = sorted(tiger_dir.glob("tl_2025_72*_roads.zip")) if tiger_dir.exists() else []
        if not zips:
            self.source_manifest.append(SourceRead("TIGER2025_ROADS_PR", "TIGER_ROADS", "T2", str(tiger_dir), False, "missing", 0, "No Census TIGER 2025 PR road zips found."))
            return
        for z in zips:
            self._read_tiger_zip(z)

    def ingest_osm_sources(self) -> None:
        osm_dir = self.source_root / "osm"
        files = []
        if osm_dir.exists():
            for ext in ("*.gpkg", "*.shp", "*.geojson", "*.json"):
                files.extend(osm_dir.rglob(ext))
            # Read inside geofabrik extracted folder if user unzips externally.
        if not files:
            self.source_manifest.append(SourceRead("OSM_GEOFABRIK_PR", "OSM_ROADS", "T3", str(osm_dir), False, "missing", 0, "No OSM road vector file found. Unzip Geofabrik GPKG/SHP first or pass extracted path."))
            return
        for path in files:
            if "road" not in path.name.lower() and "transport" not in path.name.lower() and path.suffix.lower() != ".gpkg":
                continue
            self._read_generic_road_file(path, "OSM_ROADS", "T3", f"OSM_GEOFABRIK_{path.stem}", {})

    def _read_tiger_zip(self, zip_path: Path) -> None:
        if gpd is None:
            self.source_manifest.append(SourceRead(zip_path.stem, "TIGER_ROADS", "T2", str(zip_path), True, "error", 0, "geopandas not installed."))
            return
        geoid_match = re.search(r"tl_\d{4}_(72\d{3})_roads", zip_path.name)
        municipio_geoid = geoid_match.group(1) if geoid_match else ""
        municipio_name = ""
        if not self.gov.empty and municipio_geoid:
            hit = self.gov[self.gov["municipio_geoid"].eq(municipio_geoid)]
            if not hit.empty:
                municipio_name = str(hit.iloc[0].get("county_name", "")).replace(" Municipio", "")
        try:
            gdf = gpd.read_file(f"zip://{zip_path}")
        except Exception as e:
            self.source_manifest.append(SourceRead(zip_path.stem, "TIGER_ROADS", "T2", str(zip_path), True, "error", 0, f"Read error: {e}"))
            return
        rows = 0
        for _, r in gdf.iterrows():
            mtfcc = str(r.get("MTFCC", "") or "")
            if not self.include_nonvehicular and mtfcc and mtfcc not in MFTCC_VEHICLE_CLASSES:
                continue
            fullname = str(r.get("FULLNAME", "") or "").strip()
            if not fullname:
                continue
            source_record_id = str(r.get("LINEARID", "") or r.get("TLID", "") or hashlib.sha1(str(r.to_dict()).encode("utf-8", errors="ignore")).hexdigest()[:16])
            route_number = route_number_from_text(fullname, r.get("RTTYP", ""), r.get("RTNUM", ""))
            normalized = normalize_name(fullname)
            road_id = make_road_id("TIGER_ROADS", source_record_id, route_number, normalized)
            self._append_road(
                road_id=road_id,
                source_family="TIGER_ROADS",
                source_id=zip_path.stem,
                source_record_id=source_record_id,
                canonical_name=fullname,
                normalized_name=normalized,
                route_number=route_number,
                route_ref=f"PR-{route_number}" if route_number else "",
                road_class=str(r.get("RTTYP", "") or ""),
                mtfcc=mtfcc,
                municipio_geoid=municipio_geoid,
                municipio_name=municipio_name,
                geometry=getattr(r, "geometry", None),
                geometry_source="TIGER2025_ROADS",
                source_rank="T2",
                source_dataset="CENSUS_TIGER_2025_ROADS",
                confidence=0.80,
                review_status="SOURCE_RECORD"
            )
            rows += 1
        self.source_manifest.append(SourceRead(zip_path.stem, "TIGER_ROADS", "T2", str(zip_path), True, "read", rows, "TIGER records with non-empty FULLNAME ingested."))

    def _read_generic_road_file(self, path: Path, source_family: str, source_rank: str, source_id: str, colmap: Dict) -> None:
        if gpd is None:
            self.source_manifest.append(SourceRead(source_id, source_family, source_rank, str(path), True, "error", 0, "geopandas not installed."))
            return
        try:
            if path.suffix.lower() == ".gpkg":
                # Try road-like layers first; fallback to first layer.
                import pyogrio
                layers = pyogrio.list_layers(path)
                layer_names = [str(x[0]) for x in layers]
                road_layers = [x for x in layer_names if "road" in x.lower() or "transport" in x.lower()]
                target_layers = road_layers or layer_names[:1]
                total = 0
                for layer in target_layers:
                    gdf = gpd.read_file(path, layer=layer)
                    total += self._process_generic_gdf(gdf, source_family, source_rank, f"{source_id}:{layer}", colmap)
                self.source_manifest.append(SourceRead(source_id, source_family, source_rank, str(path), True, "read", total, "Generic vector read."))
            else:
                gdf = gpd.read_file(path) if path.suffix.lower() != ".csv" else pd.read_csv(path)
                total = self._process_generic_gdf(gdf, source_family, source_rank, source_id, colmap)
                self.source_manifest.append(SourceRead(source_id, source_family, source_rank, str(path), True, "read", total, "Generic file read."))
        except Exception as e:
            self.source_manifest.append(SourceRead(source_id, source_family, source_rank, str(path), True, "error", 0, f"Read error: {e}"))

    def _first_col(self, cols: Iterable[str], candidates: Iterable[str]) -> str:
        upper = {c.upper(): c for c in cols}
        for cand in candidates:
            if cand.upper() in upper:
                return upper[cand.upper()]
        return ""

    def _process_generic_gdf(self, gdf, source_family: str, source_rank: str, source_id: str, colmap: Dict) -> int:
        cols = list(gdf.columns)
        name_col = colmap.get("road_name") or self._first_col(cols, ["FULLNAME", "NAME", "name", "STREET", "ROAD_NAME", "NOMBRE", "NOMBRE_CAR", "CALLE"])
        ref_col = colmap.get("route_number") or self._first_col(cols, ["REF", "ref", "ROUTE", "ROUTE_NUM", "RTNUM", "NUMERO", "CARRETERA", "RUTA"])
        class_col = colmap.get("road_class") or self._first_col(cols, ["FCLASS", "fclass", "MTFCC", "RTTYP", "CLASS", "TIPO"])
        muni_col = colmap.get("municipio") or self._first_col(cols, ["MUNICIPIO", "COUNTY", "COUNTYFP", "county_name", "MUNI"])
        id_col = colmap.get("source_record_id") or self._first_col(cols, ["osm_id", "OSM_ID", "LINEARID", "id", "ID", "OBJECTID", "fid"])
        rows = 0
        for i, r in gdf.iterrows():
            name = str(r.get(name_col, "") if name_col else "").strip()
            ref = str(r.get(ref_col, "") if ref_col else "").strip()
            if not name and not ref:
                continue
            canonical_name = name or f"PR-{route_number_from_text(ref)}" or ref
            route_number = route_number_from_text(ref, name)
            normalized = normalize_name(canonical_name)
            source_record_id = str(r.get(id_col, "") if id_col else i)
            road_id = make_road_id(source_family, source_record_id, route_number, normalized)
            municipio_value = str(r.get(muni_col, "") if muni_col else "").strip()
            municipio_geoid, municipio_name = self._resolve_municipio(municipio_value)
            self._append_road(
                road_id=road_id,
                source_family=source_family,
                source_id=source_id,
                source_record_id=source_record_id,
                canonical_name=canonical_name,
                normalized_name=normalized,
                route_number=route_number,
                route_ref=f"PR-{route_number}" if route_number else ref,
                road_class=str(r.get(class_col, "") if class_col else "").strip(),
                mtfcc=str(r.get("MTFCC", "") if "MTFCC" in cols else "").strip(),
                municipio_geoid=municipio_geoid,
                municipio_name=municipio_name,
                geometry=getattr(r, "geometry", None),
                geometry_source=source_family,
                source_rank=source_rank,
                source_dataset=source_id,
                confidence=0.95 if source_rank == "T1" else (0.80 if source_rank == "T2" else 0.65),
                review_status="SOURCE_RECORD"
            )
            rows += 1
        return rows

    def _resolve_municipio(self, raw: str) -> Tuple[str, str]:
        raw = str(raw or "").strip()
        if not raw:
            return "", ""
        if re.fullmatch(r"72\d{3}", raw):
            geoid = raw
            if not self.gov.empty:
                hit = self.gov[self.gov["municipio_geoid"].eq(geoid)]
                if not hit.empty:
                    return geoid, str(hit.iloc[0].get("county_name", "")).replace(" Municipio", "")
            return geoid, ""
        if re.fullmatch(r"\d{1,3}", raw):
            geoid = f"72{int(raw):03d}"
            return self._resolve_municipio(geoid)
        if not self.gov.empty:
            norm = normalize_name(raw).replace(" MUNICIPIO", "")
            tmp = self.gov.copy()
            tmp["_norm"] = tmp["county_name"].fillna("").map(lambda x: normalize_name(str(x)).replace(" MUNICIPIO", ""))
            hit = tmp[tmp["_norm"].eq(norm)]
            if not hit.empty:
                return str(hit.iloc[0].get("municipio_geoid", "")), str(hit.iloc[0].get("county_name", "")).replace(" Municipio", "")
        return "", raw

    def _append_road(self, road_id: str, source_family: str, source_id: str, source_record_id: str, canonical_name: str, normalized_name: str, route_number: str, route_ref: str, road_class: str, mtfcc: str, municipio_geoid: str, municipio_name: str, geometry, geometry_source: str, source_rank: str, source_dataset: str, confidence, review_status: str) -> None:
        geom_type = ""
        if geometry is not None:
            try:
                geom_type = geometry.geom_type
            except Exception:
                geom_type = ""
        self.canonical_rows.append({
            'spiderweb_road_id': road_id,
            'source_family': source_family,
            'source_id': source_id,
            'source_record_id': source_record_id,
            'canonical_name': canonical_name,
            'normalized_name': normalized_name,
            'route_number': route_number,
            'route_ref': route_ref,
            'road_class': road_class,
            'mtfcc': mtfcc,
            'municipio_geoid': municipio_geoid,
            'municipio_name': municipio_name,
            'geometry_type': geom_type,
            'geometry_wkt': safe_wkt(geometry),
            'geometry_source': geometry_source,
            'source_rank': source_rank,
            'source_dataset': source_dataset,
            'confidence': confidence,
            'review_status': review_status,
            'ingested_at_utc': self.now,
        })
        for name, typ in alias_variants(route_number, canonical_name):
            if typ == "canonical":
                source_type = 'dtop_name' if source_family == 'DTOP_ROUTE_DATA' else ('tiger_fullname' if source_family == 'TIGER_ROADS' else 'osm_name')
            else:
                source_type = typ
            self.name_rows.append({
                'spiderweb_road_id': road_id,
                'source_family': source_family,
                'source_id': source_id,
                'source_record_id': source_record_id,
                'name_value': name,
                'normalized_name': normalize_name(name),
                'name_type': source_type,
                'language': 'mixed',
                'route_number': route_number,
                'source_rank': source_rank,
                'source_dataset': source_dataset,
                'review_status': review_status,
            })
        if municipio_geoid:
            self.edge_rows.append({
                'spiderweb_road_id': road_id,
                'municipio_geoid': municipio_geoid,
                'municipio_name': municipio_name,
                'edge_type': 'LOCATED_IN_MUNICIPIO',
                'source_family': source_family,
                'source_id': source_id,
                'confidence': confidence,
                'review_status': review_status,
            })

    def detect_conflicts(self) -> None:
        if not self.canonical_rows:
            return
        df = pd.DataFrame(self.canonical_rows)
        # Conflict heuristic: same route number + municipio, multiple materially different canonical names from different source families.
        idx = 0
        subset = df[df['route_number'].fillna('').ne('')].copy()
        for (rn, geoid), g in subset.groupby(['route_number', 'municipio_geoid'], dropna=False):
            names = sorted(set(g['normalized_name'].dropna()))
            sources = sorted(set(g['source_family'].dropna()))
            if len(names) > 1 and len(sources) > 1:
                idx += 1
                self.conflict_rows.append({
                    'conflict_id': f'road_conflict:{idx:06d}',
                    'conflict_type': 'ROUTE_NAME_VARIANCE_BY_SOURCE',
                    'normalized_key': f'PR-{rn}|{geoid}',
                    'route_number': rn,
                    'municipio_geoid': geoid,
                    'municipio_name': ', '.join(sorted(set(g['municipio_name'].fillna('').astype(str))))[:250],
                    'source_a': sources[0] if sources else '',
                    'source_b': sources[-1] if sources else '',
                    'value_a': names[0] if names else '',
                    'value_b': names[-1] if names else '',
                    'severity': 'MEDIUM',
                    'resolution_status': 'OPEN',
                    'notes': 'Same route number in same municipio has different road-name strings across sources.'
                })

    def write_outputs(self) -> None:
        headers = {
            'road_canonical_features.csv': ['spiderweb_road_id','source_family','source_id','source_record_id','canonical_name','normalized_name','route_number','route_ref','road_class','mtfcc','municipio_geoid','municipio_name','geometry_type','geometry_wkt','geometry_source','source_rank','source_dataset','confidence','review_status','ingested_at_utc'],
            'road_feature_names.csv': ['spiderweb_road_id','source_family','source_id','source_record_id','name_value','normalized_name','name_type','language','route_number','source_rank','source_dataset','review_status'],
            'road_municipio_edges.csv': ['spiderweb_road_id','municipio_geoid','municipio_name','edge_type','source_family','source_id','confidence','review_status'],
            'road_source_conflicts.csv': ['conflict_id','conflict_type','normalized_key','route_number','municipio_geoid','municipio_name','source_a','source_b','value_a','value_b','severity','resolution_status','notes'],
        }
        for fn, rows in [
            ('road_canonical_features.csv', self.canonical_rows),
            ('road_feature_names.csv', self.name_rows),
            ('road_municipio_edges.csv', self.edge_rows),
            ('road_source_conflicts.csv', self.conflict_rows),
        ]:
            pd.DataFrame(rows, columns=headers[fn]).to_csv(self.output_dir / fn, index=False)
        pd.DataFrame([s.__dict__ for s in self.source_manifest]).to_csv(self.output_dir / 'road_ingest_source_manifest.csv', index=False)
        report = {
            'vector': 'SPIDERWEB_ROAD_NAME_GAZETTEER_INGEST',
            'created_at_utc': self.now,
            'canonical_road_rows': len(self.canonical_rows),
            'road_name_rows': len(self.name_rows),
            'road_municipio_edge_rows': len(self.edge_rows),
            'road_source_conflict_rows': len(self.conflict_rows),
            'source_manifest_rows': len(self.source_manifest),
            'source_status_counts': pd.Series([s.status for s in self.source_manifest]).value_counts().to_dict() if self.source_manifest else {},
            'gnis_duplication_guard': 'Only road:* namespace emitted; GNIS non-road records are not copied into road outputs.',
        }
        (self.output_dir / 'road_ingest_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-root', default='data/reference/roads/raw')
    ap.add_argument('--gnis-dir', default='data/reference/gazetteer/processed')
    ap.add_argument('--output-dir', default='data/reference/roads/processed')
    ap.add_argument('--include-nonvehicular', action='store_true')
    args = ap.parse_args()
    RoadGazetteerIngest(Path(args.source_root), Path(args.gnis_dir), Path(args.output_dir), include_nonvehicular=args.include_nonvehicular).run()

if __name__ == '__main__':
    main()
