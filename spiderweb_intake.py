"""
SPIDERWEB INTAKE
Consumes the five --export-spiderweb bridge files and produces a normalized
Spiderweb overlay layer with MBIL/hydro/utility/terrain scoring and a gap audit.

This module is Spiderweb-native: it reads the producer boundary as-is and
does not modify any PRII modules (pr_intel_adapter, schema_validation, etc.).
"""

import csv
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Producer boundary ─────────────────────────────────────────────────────────

BRIDGE_FILES = [
    "airspace_poi_candidates.geojson",
    "airspace_ilap_candidates.geojson",
    "airspace_corridor_candidates.geojson",
    "aasb_airspace_edges.csv",
    "spiderweb_ingest_manifest.json",
]

# ── Required Spiderweb output fields ─────────────────────────────────────────

REQUIRED_FIELDS = [
    "source_layer", "candidate_type", "lat", "lon", "confidence",
    "evidence_tier", "linked_flight_id", "linked_aircraft", "corridor_id",
    "mbil_class", "hydro_overlap", "utility_overlap", "terrain_context",
    "review_status",
]

# ── Scoring constants ─────────────────────────────────────────────────────────

DEDUP_THRESH_DEG = 0.00045   # ≈50 m

# PR municipal centroids (subset of 72 municipalities; key urban/boundary nodes)
MUNICIPAL_CENTROIDS: List[Tuple[float, float]] = [
    (18.4655, -66.1057),  # San Juan
    (18.0099, -66.6140),  # Ponce
    (18.4279, -66.7177),  # Mayagüez
    (18.4906, -67.1414),  # Aguadilla
    (18.3990, -65.9732),  # Carolina
    (18.3449, -66.0498),  # Guaynabo
    (18.3804, -65.8754),  # Loíza
    (18.2218, -66.0370),  # Cayey
    (18.0791, -66.5293),  # Juana Díaz
    (18.2499, -65.8960),  # Humacao
    (18.4735, -66.9008),  # San Germán
    (18.1466, -65.9965),  # Salinas
    (18.3660, -66.4696),  # Barceloneta
    (18.2302, -66.3068),  # Aibonito
    (18.4562, -66.5551),  # Arecibo
    (18.1306, -66.7327),  # Yauco
    (18.4284, -66.1617),  # Bayamón
    (18.4014, -66.2956),  # Toa Baja
    (18.4449, -66.6188),  # Camuy
    (18.3002, -65.6340),  # Fajardo
]

# PR reservoirs / major water bodies
HYDRO_LOCATIONS: List[Tuple[float, float]] = [
    (18.3517, -66.3200),  # Lago La Plata
    (18.3333, -66.7167),  # Lago Dos Bocas
    (18.3667, -65.9833),  # Lago Loíza
    (18.1167, -66.5333),  # Lago Toa Vaca
    (18.0500, -66.5667),  # Embalse Cerrillos
    (18.1667, -66.2167),  # Lago Cidra
    (18.2667, -65.7833),  # Lago Humacao
    (18.1333, -66.4167),  # Lago Coamo
]
HYDRO_THRESH_DEG = 0.08   # ≈9 km

# SJU↔PSE and SJU↔BQN corridor midpoint+bearing heuristic (simplified as waypoints)
UTILITY_CORRIDOR_WAYPOINTS: List[Tuple[float, float]] = [
    (18.4373, -66.0018),  # SJU
    (18.2600, -66.3000),  # midpoint SJU–PSE
    (18.0083, -66.5632),  # PSE
    (18.3700, -66.5500),  # midpoint SJU–BQN
    (18.4948, -67.1294),  # BQN
    (18.4000, -66.8500),  # Mayagüez corridor waypoint
]
UTILITY_THRESH_DEG = 0.05  # ≈5 km

# SJU metro bounding box
URBAN_LAT = (18.35, 18.50)
URBAN_LON = (-66.20, -65.90)

# PR longitude bounds — beyond these is open ocean → coastal
PR_LON_WEST = -67.30
PR_LON_EAST = -65.50

CONFIDENCE_T1 = 0.65
CONFIDENCE_T2 = 0.40
CONFIDENCE_REJECTED = 0.25


# ── Main class ────────────────────────────────────────────────────────────────

class SpiderwebIntake:
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        candidates = self._load_candidates()
        self._normalize(candidates)
        missing_files = self._missing_bridge_files()
        dups_removed, candidates = self._dedup(candidates, DEDUP_THRESH_DEG)
        self._score_mbil(candidates)
        self._score_hydro(candidates)
        self._score_utility(candidates)
        self._score_terrain(candidates)
        self._assign_evidence_tier(candidates)
        gap_audit = self._gap_audit(candidates, missing_files, dups_removed)
        self._write_outputs(candidates, gap_audit)
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_candidates": len(candidates),
            "output_dir": str(self.output_dir),
            "gap_audit": gap_audit,
        }

    # ── Loader ────────────────────────────────────────────────────────────────

    def _load_candidates(self) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        for geojson_file, ctype in [
            ("airspace_poi_candidates.geojson", "poi"),
            ("airspace_ilap_candidates.geojson", "ilap"),
            ("airspace_corridor_candidates.geojson", "corridor"),
        ]:
            path = self.input_dir / geojson_file
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for feat in data.get("features", []):
                geom = feat.get("geometry", {})
                props = feat.get("properties", {}) or {}
                lat, lon = self._centroid(geom)
                if lat is None:
                    continue
                candidates.append({
                    "_raw_props": props,
                    "_candidate_type": ctype,
                    "_lat": lat,
                    "_lon": lon,
                })

        edge_path = self.input_dir / "aasb_airspace_edges.csv"
        if edge_path.exists():
            try:
                with open(edge_path, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        from_lat = _safe_float(row.get("from_lat"))
                        from_lon = _safe_float(row.get("from_lon"))
                        to_lat = _safe_float(row.get("to_lat"))
                        to_lon = _safe_float(row.get("to_lon"))
                        if from_lat is None or to_lat is None:
                            continue
                        lat = (from_lat + to_lat) / 2.0
                        lon = (from_lon + to_lon) / 2.0
                        candidates.append({
                            "_raw_props": dict(row),
                            "_candidate_type": "aasb_edge",
                            "_lat": lat,
                            "_lon": lon,
                        })
            except Exception:
                pass

        return candidates

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _normalize(self, candidates: List[Dict[str, Any]]) -> None:
        for c in candidates:
            props = c["_raw_props"]
            ctype = c["_candidate_type"]

            confidence = _inherit_confidence(props, ctype)
            linked_flight_id = props.get("flight_id") or None
            linked_aircraft = props.get("callsign") or props.get("dominant_callsign") or None
            corridor_id = _corridor_id(props, ctype)

            c.update({
                "source_layer": "airspace_spiderweb_export",
                "candidate_type": ctype,
                "lat": round(c["_lat"], 6),
                "lon": round(c["_lon"], 6),
                "confidence": round(confidence, 4),
                "evidence_tier": None,       # set later
                "linked_flight_id": linked_flight_id,
                "linked_aircraft": linked_aircraft,
                "corridor_id": corridor_id,
                "mbil_class": None,          # set later
                "hydro_overlap": "unknown",  # set later
                "utility_overlap": "unknown",
                "terrain_context": "unknown",
                "review_status": None,       # set later
            })

    # ── Dedup ─────────────────────────────────────────────────────────────────

    def _dedup(
        self, candidates: List[Dict[str, Any]], thresh_deg: float
    ) -> Tuple[int, List[Dict[str, Any]]]:
        kept: List[Dict[str, Any]] = []
        for c in candidates:
            lat, lon = c["_lat"], c["_lon"]
            duplicate = any(
                abs(k["_lat"] - lat) <= thresh_deg and abs(k["_lon"] - lon) <= thresh_deg
                for k in kept
            )
            if not duplicate:
                kept.append(c)
        return len(candidates) - len(kept), kept

    # ── MBIL scoring ──────────────────────────────────────────────────────────

    def _score_mbil(self, candidates: List[Dict[str, Any]]) -> None:
        for c in candidates:
            dist = _min_dist_deg(c["_lat"], c["_lon"], MUNICIPAL_CENTROIDS)
            dist_km = dist * 111.0
            if dist_km < 5.0:
                c["mbil_class"] = "MBIL-3"
            elif dist_km < 10.0:
                c["mbil_class"] = "MBIL-2"
            elif dist_km < 15.0:
                c["mbil_class"] = "MBIL-1"
            else:
                c["mbil_class"] = "MBIL-0"

    # ── Hydro scoring ─────────────────────────────────────────────────────────

    def _score_hydro(self, candidates: List[Dict[str, Any]]) -> None:
        for c in candidates:
            dist = _min_dist_deg(c["_lat"], c["_lon"], HYDRO_LOCATIONS)
            c["hydro_overlap"] = "yes" if dist <= HYDRO_THRESH_DEG else "no"

    # ── Utility scoring ───────────────────────────────────────────────────────

    def _score_utility(self, candidates: List[Dict[str, Any]]) -> None:
        for c in candidates:
            dist = _min_dist_deg(c["_lat"], c["_lon"], UTILITY_CORRIDOR_WAYPOINTS)
            c["utility_overlap"] = "yes" if dist <= UTILITY_THRESH_DEG else "no"

    # ── Terrain scoring ───────────────────────────────────────────────────────

    def _score_terrain(self, candidates: List[Dict[str, Any]]) -> None:
        for c in candidates:
            lat, lon = c["_lat"], c["_lon"]
            if URBAN_LAT[0] <= lat <= URBAN_LAT[1] and URBAN_LON[0] <= lon <= URBAN_LON[1]:
                c["terrain_context"] = "urban"
            elif lon <= PR_LON_WEST or lon >= PR_LON_EAST:
                c["terrain_context"] = "coastal"
            else:
                c["terrain_context"] = "inland"

    # ── Evidence tier ─────────────────────────────────────────────────────────

    def _assign_evidence_tier(self, candidates: List[Dict[str, Any]]) -> None:
        for c in candidates:
            conf = c["confidence"]
            props = c["_raw_props"]
            ctype = c["candidate_type"]

            corroborating = sum([
                c["hydro_overlap"] == "yes",
                c["utility_overlap"] == "yes",
                c["mbil_class"] != "MBIL-0",
                c["corridor_id"] is not None,
            ])

            corridor_align = _safe_float(props.get("corridor_alignment_score")) or 0.0
            connecting = int(props.get("connecting_flights") or 0)

            if conf >= CONFIDENCE_T1 and corroborating >= 2:
                tier = "T1"
            elif ctype == "corridor" and connecting >= 2:
                # Corridors with ≥2 connecting flights are T3 (manual review)
                # unless they already qualify for T1 via confidence + corroboration
                tier = "T3"
            elif conf >= CONFIDENCE_T2 or corridor_align > 0.5:
                tier = "T2"
            else:
                tier = "T4"

            c["evidence_tier"] = tier

            if tier in ("T1", "T2"):
                c["review_status"] = "accepted"
            elif tier == "T3":
                c["review_status"] = "manual_review"
            else:
                c["review_status"] = "rejected" if conf < CONFIDENCE_REJECTED else "manual_review"

    # ── Gap audit ─────────────────────────────────────────────────────────────

    def _gap_audit(
        self,
        candidates: List[Dict[str, Any]],
        missing_files: List[str],
        dups_removed: int,
    ) -> Dict[str, Any]:
        total = len(candidates)

        isolated = sum(
            1 for c in candidates
            if c.get("corridor_id") is None and c["candidate_type"] == "poi"
        )
        no_evidence = sum(
            1 for c in candidates
            if c["hydro_overlap"] == "no" and c["utility_overlap"] == "no"
        )
        unclustered = sum(
            1 for c in candidates
            if c["candidate_type"] == "ilap"
            and (_safe_float(c["_raw_props"].get("corridor_alignment_score")) or 0.0) < 0.3
        )
        mbil_0 = sum(1 for c in candidates if c.get("mbil_class") == "MBIL-0")
        pct_low = round(mbil_0 / total, 4) if total else 0.0

        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_candidates": total,
            "after_dedup": total,
            "gaps": {
                "export_gap":   {"missing_files": missing_files},
                "dedup_gap":    {"duplicates_removed": dups_removed, "threshold_deg": DEDUP_THRESH_DEG},
                "spatial_gap":  {"isolated_candidates": isolated},
                "evidence_gap": {"no_hydro_or_utility": no_evidence},
                "temporal_gap": {"unclustered_routes": unclustered},
                "mbil_gap":     {"mbil_0_count": mbil_0, "pct_low_mbil": pct_low},
            },
        }

    # ── Output writers ────────────────────────────────────────────────────────

    def _write_outputs(
        self, candidates: List[Dict[str, Any]], gap_audit: Dict[str, Any]
    ) -> None:
        features = []
        for c in candidates:
            props = {k: c[k] for k in REQUIRED_FIELDS}
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": props,
            })

        overlay = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
            "features": features,
        }
        (self.output_dir / "spiderweb_overlay_candidates.geojson").write_text(
            json.dumps(overlay, indent=2), encoding="utf-8"
        )
        (self.output_dir / "spiderweb_gap_audit.json").write_text(
            json.dumps(gap_audit, indent=2), encoding="utf-8"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _missing_bridge_files(self) -> List[str]:
        return [f for f in BRIDGE_FILES if not (self.input_dir / f).exists()]

    def _centroid(self, geom: dict) -> Tuple[Optional[float], Optional[float]]:
        gtype = geom.get("type", "")
        coords = geom.get("coordinates")
        if not coords:
            return None, None
        if gtype == "Point":
            return coords[1], coords[0]
        if gtype == "LineString" and coords:
            lats = [p[1] for p in coords]
            lons = [p[0] for p in coords]
            return sum(lats) / len(lats), sum(lons) / len(lons)
        return None, None


# ── Module-level helpers ──────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _min_dist_deg(lat: float, lon: float, refs: List[Tuple[float, float]]) -> float:
    if not refs:
        return float("inf")
    return min(math.hypot(lat - r[0], lon - r[1]) for r in refs)


def _inherit_confidence(props: dict, ctype: str) -> float:
    if ctype == "poi":
        return _safe_float(props.get("overall_confidence")) or 0.0
    if ctype == "ilap":
        return _safe_float(props.get("corridor_alignment_score")) or 0.0
    if ctype == "corridor":
        flights = int(props.get("connecting_flights") or 0)
        return min(1.0, flights / 5.0)
    if ctype == "aasb_edge":
        return _safe_float(props.get("confidence_score")) or 0.0
    return 0.0


def _corridor_id(props: dict, ctype: str) -> Optional[str]:
    if ctype == "corridor":
        a = props.get("poi_a")
        b = props.get("poi_b")
        if a and b:
            return f"{a}|{b}"
    if ctype == "aasb_edge":
        return props.get("edge_id") or None
    if ctype == "ilap":
        fid = props.get("flight_id")
        return f"ILAP_{fid}" if fid else None
    return None
