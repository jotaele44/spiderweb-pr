"""Tests for ILAPAirspaceBridge: POI candidates and infrastructure alignment."""

import json
import sqlite3
from pathlib import Path

from ilap_airspace_bridge import ILAPAirspaceBridge


def _make_db(tmp_path: Path, track_rows: list) -> str:
    db = str(tmp_path / "ilap.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE track_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT, flight_id TEXT,
            timestamp TEXT, latitude REAL, longitude REAL,
            altitude_ft INTEGER, ground_speed_mph INTEGER
        )"""
    )
    conn.executemany(
        "INSERT INTO track_points (flight_id, timestamp, latitude, longitude, "
        "altitude_ft, ground_speed_mph) VALUES (?,?,?,?,?,?)",
        track_rows,
    )
    conn.commit()
    conn.close()
    return db


def test_infra_alignment_score_high_near_infrastructure(tmp_path):
    bridge = ILAPAirspaceBridge(_make_db(tmp_path, []), str(tmp_path / "out"))
    # PREPA_SOUTH_CORRIDOR sits at 18.0, -66.5.
    score = bridge._infra_alignment_score(18.0, -66.5)
    assert score > 0.5


def test_infra_alignment_score_zero_far_from_pr(tmp_path):
    bridge = ILAPAirspaceBridge(_make_db(tmp_path, []), str(tmp_path / "out"))
    # Mid-Atlantic, far from any Puerto Rico infrastructure.
    assert bridge._infra_alignment_score(25.0, -60.0) == 0.0


def test_poi_candidate_reports_real_infra_alignment(tmp_path):
    # A loitering cluster (>=3 points, >=2 flights) near the south-coast
    # transmission corridor should score a non-trivial infra alignment.
    rows = [
        ("FLT_A", "2024-03-15T08:00:00", 18.01, -66.49, 1200, 20),
        ("FLT_B", "2024-03-15T08:05:00", 18.02, -66.48, 1100, 15),
        ("FLT_A", "2024-03-15T08:10:00", 18.03, -66.47, 1300, 10),
    ]
    db = _make_db(tmp_path, rows)
    bridge = ILAPAirspaceBridge(db, str(tmp_path / "out"))
    bridge.export_all()

    poi = json.loads((tmp_path / "out" / "airspace_poi_candidates.geojson").read_text())
    assert len(poi["features"]) == 1
    props = poi["features"][0]["properties"]
    assert props["infra_alignment_score"] > 0.0
    # The score is now data-derived, not the old flat 0.3 placeholder.
    assert props["infra_alignment_score"] != 0.3
