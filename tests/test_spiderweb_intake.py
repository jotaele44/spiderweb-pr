"""Tests for spiderweb_intake.py: normalization, dedup, scoring, gap audit."""

import csv
import json
from pathlib import Path

import pytest

from spiderweb_intake import (
    BRIDGE_FILES,
    DEDUP_THRESH_DEG,
    REQUIRED_FIELDS,
    SpiderwebIntake,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}

def _write_poi(tmp_path: Path, features=None) -> None:
    if features is None:
        features = [_poi_feature(18.35, -66.32)]
    fc = {"type": "FeatureCollection", "crs": CRS, "features": features}
    (tmp_path / "airspace_poi_candidates.geojson").write_text(json.dumps(fc))


def _write_ilap(tmp_path: Path, features=None) -> None:
    if features is None:
        features = [_ilap_feature("FLT_001", "N5854Z", 0.7)]
    fc = {"type": "FeatureCollection", "crs": CRS, "features": features}
    (tmp_path / "airspace_ilap_candidates.geojson").write_text(json.dumps(fc))


def _write_corridor(tmp_path: Path, features=None) -> None:
    if features is None:
        features = [_corridor_feature(18.35, -66.32, 18.45, -66.10, 3)]
    fc = {"type": "FeatureCollection", "crs": CRS, "features": features}
    (tmp_path / "airspace_corridor_candidates.geojson").write_text(json.dumps(fc))


def _write_edges(tmp_path: Path, rows=None) -> None:
    if rows is None:
        rows = [_edge_row()]
    fieldnames = [
        "edge_id", "from_node", "to_node",
        "from_lat", "from_lon", "to_lat", "to_lon",
        "weight", "flight_count", "avg_duration_min",
        "dominant_callsign", "confidence_score",
    ]
    with open(tmp_path / "aasb_airspace_edges.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _write_manifest(tmp_path: Path) -> None:
    manifest = {
        "generated_at": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
        "files": [],
    }
    (tmp_path / "spiderweb_ingest_manifest.json").write_text(json.dumps(manifest))


def _write_all_five(tmp_path: Path) -> None:
    _write_poi(tmp_path)
    _write_ilap(tmp_path)
    _write_corridor(tmp_path)
    _write_edges(tmp_path)
    _write_manifest(tmp_path)


def _poi_feature(lat, lon, confidence=0.5):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "lat": lat, "lon": lon,
            "overall_confidence": confidence,
            "review_priority": "MEDIUM",
            "identity_note": "not standalone evidence",
        },
    }


def _ilap_feature(flight_id, callsign, corridor_score):
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[-66.0, 18.4], [-66.5, 18.1]],
        },
        "properties": {
            "flight_id": flight_id,
            "callsign": callsign,
            "corridor_alignment_score": corridor_score,
            "mission_type": "patrol",
            "identity_note": "not standalone evidence",
        },
    }


def _corridor_feature(lat1, lon1, lat2, lon2, connecting_flights=3):
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon1, lat1], [lon2, lat2]],
        },
        "properties": {
            "poi_a": f"{lat1},{lon1}",
            "poi_b": f"{lat2},{lon2}",
            "connecting_flights": connecting_flights,
            "identity_note": "not standalone evidence",
        },
    }


def _edge_row(edge_id="EDGE_0000_SJU_PSE", from_node="SJU", to_node="PSE",
              from_lat=18.4373, from_lon=-66.0018,
              to_lat=18.0083, to_lon=-66.5632,
              weight=5, flight_count=5, avg_duration_min=45.0,
              dominant_callsign="N5854Z", confidence_score=1.0):
    return {
        "edge_id": edge_id,
        "from_node": from_node, "to_node": to_node,
        "from_lat": from_lat, "from_lon": from_lon,
        "to_lat": to_lat, "to_lon": to_lon,
        "weight": weight, "flight_count": flight_count,
        "avg_duration_min": avg_duration_min,
        "dominant_callsign": dominant_callsign,
        "confidence_score": confidence_score,
    }


# ── Phase A: intake runs cleanly ──────────────────────────────────────────────

def test_intake_runs_on_empty_dir(tmp_path):
    result = SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    assert "gap_audit" in result
    assert result["total_candidates"] == 0
    assert len(result["gap_audit"]["gaps"]["export_gap"]["missing_files"]) == len(BRIDGE_FILES)


def test_intake_runs_on_full_five_file_set(tmp_path):
    _write_all_five(tmp_path)
    result = SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    assert result["total_candidates"] > 0
    assert result["gap_audit"]["gaps"]["export_gap"]["missing_files"] == []


# ── Phase B: candidate loading and normalization ──────────────────────────────

def test_intake_loads_poi_candidates(tmp_path):
    _write_poi(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    pois = [f for f in data["features"] if f["properties"]["candidate_type"] == "poi"]
    assert len(pois) == 1
    assert pois[0]["properties"]["source_layer"] == "airspace_spiderweb_export"


def test_intake_loads_ilap_candidates(tmp_path):
    _write_ilap(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    ilaps = [f for f in data["features"] if f["properties"]["candidate_type"] == "ilap"]
    assert len(ilaps) == 1
    assert ilaps[0]["properties"]["linked_flight_id"] == "FLT_001"


def test_intake_loads_corridor_candidates(tmp_path):
    _write_corridor(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    corridors = [f for f in data["features"] if f["properties"]["candidate_type"] == "corridor"]
    assert len(corridors) == 1
    assert corridors[0]["properties"]["corridor_id"] is not None


def test_intake_loads_aasb_edges(tmp_path):
    _write_edges(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    edges = [f for f in data["features"] if f["properties"]["candidate_type"] == "aasb_edge"]
    assert len(edges) == 1
    assert edges[0]["properties"]["corridor_id"] == "EDGE_0000_SJU_PSE"


# ── Dedup ─────────────────────────────────────────────────────────────────────

def test_dedup_removes_near_duplicates(tmp_path):
    # Two POIs within DEDUP_THRESH_DEG → only 1 kept
    feats = [
        _poi_feature(18.35, -66.32),
        _poi_feature(18.35 + DEDUP_THRESH_DEG * 0.5, -66.32 + DEDUP_THRESH_DEG * 0.5),
    ]
    _write_poi(tmp_path, features=feats)
    result = SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    assert result["gap_audit"]["gaps"]["dedup_gap"]["duplicates_removed"] == 1
    assert result["total_candidates"] == 1


def test_dedup_keeps_distant_candidates(tmp_path):
    feats = [_poi_feature(18.35, -66.32), _poi_feature(18.45, -66.10)]
    _write_poi(tmp_path, features=feats)
    result = SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    assert result["total_candidates"] == 2
    assert result["gap_audit"]["gaps"]["dedup_gap"]["duplicates_removed"] == 0


# ── Evidence tier and review status ──────────────────────────────────────────

def test_evidence_tier_t1_requires_two_corroborating_signals(tmp_path):
    # Lago La Plata coords + utility corridor → hydro=yes, utility=yes; confidence≥0.65 → T1
    feats = [_poi_feature(18.3517, -66.3200, confidence=0.80)]
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    props = data["features"][0]["properties"]
    assert props["evidence_tier"] == "T1"
    assert props["review_status"] == "accepted"


def test_evidence_tier_t4_for_low_confidence_no_signals(tmp_path):
    # Far from everything, low confidence → T4, rejected
    feats = [_poi_feature(17.95, -65.55, confidence=0.10)]
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    props = data["features"][0]["properties"]
    assert props["evidence_tier"] == "T4"
    assert props["review_status"] == "rejected"


def test_review_status_manual_for_t3(tmp_path):
    # Corridor with ≥2 connecting flights but no high confidence → T3, manual_review
    feats = [_corridor_feature(17.98, -65.62, 18.05, -65.70, connecting_flights=2)]
    _write_corridor(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    props = data["features"][0]["properties"]
    assert props["evidence_tier"] == "T3"
    assert props["review_status"] == "manual_review"


# ── Hydro scoring ─────────────────────────────────────────────────────────────

def test_hydro_overlap_near_lago_la_plata(tmp_path):
    feats = [_poi_feature(18.3517, -66.3200)]
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    assert data["features"][0]["properties"]["hydro_overlap"] == "yes"


# ── MBIL scoring ──────────────────────────────────────────────────────────────

def test_mbil_class_near_san_juan(tmp_path):
    feats = [_poi_feature(18.4655, -66.1057)]
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    assert data["features"][0]["properties"]["mbil_class"] == "MBIL-3"


def test_mbil_class_remote_location(tmp_path):
    feats = [_poi_feature(17.92, -65.52)]  # far from all centroids
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    assert data["features"][0]["properties"]["mbil_class"] == "MBIL-0"


# ── Terrain scoring ───────────────────────────────────────────────────────────

def test_terrain_coastal_west(tmp_path):
    feats = [_poi_feature(18.49, -67.35)]  # beyond PR_LON_WEST
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    assert data["features"][0]["properties"]["terrain_context"] == "coastal"


def test_terrain_urban_sju(tmp_path):
    feats = [_poi_feature(18.42, -66.06)]
    _write_poi(tmp_path, features=feats)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    assert data["features"][0]["properties"]["terrain_context"] == "urban"


# ── Output files ──────────────────────────────────────────────────────────────

def test_overlay_geojson_created(tmp_path):
    _write_all_five(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    overlay_path = tmp_path / "spiderweb_overlay_candidates.geojson"
    assert overlay_path.exists()
    data = json.loads(overlay_path.read_text())
    assert data["type"] == "FeatureCollection"
    assert "4326" in data["crs"]["properties"]["name"]


def test_gap_audit_json_created(tmp_path):
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    audit_path = tmp_path / "spiderweb_gap_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    expected_gaps = {"export_gap", "dedup_gap", "spatial_gap", "evidence_gap", "temporal_gap", "mbil_gap"}
    assert set(audit["gaps"].keys()) == expected_gaps


def test_export_gap_detects_missing_file(tmp_path):
    # Only write 4 of 5 files (no manifest)
    _write_poi(tmp_path)
    _write_ilap(tmp_path)
    _write_corridor(tmp_path)
    _write_edges(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    audit = json.loads((tmp_path / "spiderweb_gap_audit.json").read_text())
    assert "spiderweb_ingest_manifest.json" in audit["gaps"]["export_gap"]["missing_files"]


def test_all_required_fields_present(tmp_path):
    _write_all_five(tmp_path)
    SpiderwebIntake(str(tmp_path), str(tmp_path)).run()
    data = json.loads((tmp_path / "spiderweb_overlay_candidates.geojson").read_text())
    for feat in data["features"]:
        for field in REQUIRED_FIELDS:
            assert field in feat["properties"], f"Missing field: {field}"
