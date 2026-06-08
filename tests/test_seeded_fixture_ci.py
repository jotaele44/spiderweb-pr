import json
import sqlite3
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHA64 = "a" * 64


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "run_all.py"] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _run_script(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _seed_flight_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE flights (
            flight_id TEXT PRIMARY KEY,
            callsign TEXT,
            aircraft_type TEXT,
            operator TEXT,
            origin_airport TEXT,
            destination_airport TEXT,
            takeoff_time TEXT,
            landing_time TEXT,
            flight_duration_minutes INTEGER,
            max_altitude_ft INTEGER,
            avg_speed_mph REAL,
            mission_type TEXT,
            origin_lat REAL,
            origin_lon REAL,
            dest_lat REAL,
            dest_lon REAL,
            num_screenshots INTEGER,
            corridor_alignment_score REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE screenshots (
            screenshot_id TEXT PRIMARY KEY,
            image_path TEXT,
            flight_id TEXT,
            processed_at TEXT,
            callsign TEXT,
            altitude_ft INTEGER,
            ground_speed_mph INTEGER,
            latitude REAL,
            longitude REAL,
            timestamp TEXT,
            raw_text TEXT,
            ocr_confidence REAL,
            sha256 TEXT,
            coordinate_method TEXT,
            coordinate_confidence REAL,
            estimated_error_m REAL,
            review_status TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE track_points (
            id INTEGER PRIMARY KEY,
            flight_id TEXT,
            timestamp TEXT,
            latitude REAL,
            longitude REAL,
            altitude_ft INTEGER,
            ground_speed_mph INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE mission_scores (
            flight_id TEXT,
            mission_type TEXT,
            total_score REAL,
            confidence_level TEXT,
            signal_scores TEXT,
            explanation TEXT,
            scored_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE alerts (
            alert_id TEXT PRIMARY KEY,
            flight_id TEXT,
            callsign TEXT,
            category TEXT,
            severity TEXT,
            title TEXT,
            description TEXT,
            evidence TEXT,
            timestamp TEXT,
            recommended_action TEXT,
            auto_resolved INTEGER,
            acknowledged INTEGER,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE aircraft_profiles (
            callsign TEXT PRIMARY KEY,
            aircraft_type TEXT,
            operator TEXT,
            primary_mission TEXT,
            confidence_level REAL,
            last_seen TEXT,
            total_flights INTEGER
        )
        """
    )

    flights = [
        (
            "FL001", "N5854Z", "Airbus H125", "PREPA", "SJU", "PSE",
            "2024-03-15T08:00:00", "2024-03-15T08:35:00", 35, 2400, 95.0,
            "powerline_inspection", 18.4373, -66.0018, 18.0083, -66.5632,
            1, 0.75,
        ),
        (
            "FL002", "N767PD", "Bell 429", "FURA", "SJU", "BQN",
            "2024-03-15T09:00:00", "2024-03-15T09:42:00", 42, 2600, 105.0,
            "law_enforcement", 18.4373, -66.0018, 18.4948, -67.1294,
            1, 0.65,
        ),
        (
            "FL003", "C6062", "MH-60T", "USCG", "BQN", "SJU",
            "2024-03-15T10:00:00", "2024-03-15T10:50:00", 50, 3200, 120.0,
            "maritime_patrol", 18.4948, -67.1294, 18.4373, -66.0018,
            1, 0.55,
        ),
    ]
    cur.executemany(
        "INSERT INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        flights,
    )

    screenshots = [
        (
            "SS001", "fixtures/fr24/ss001.png", "FL001", "2024-03-15T08:36:00Z",
            "N5854Z", 1200, 45, 18.4373, -66.0018, "2024-03-15T08:05:00",
            "N5854Z SJU PSE", 0.91, SHA64, "fixed_pr_bounds", 0.86, 250.0,
            "approved",
        ),
        (
            "SS002", "fixtures/fr24/ss002.png", "FL002", "2024-03-15T09:43:00Z",
            "N767PD", 1400, 50, 18.4380, -66.0020, "2024-03-15T09:05:00",
            "N767PD SJU BQN", 0.88, SHA64, "fixed_pr_bounds", 0.84, 275.0,
            "approved",
        ),
        (
            "SS003", "fixtures/fr24/ss003.png", "FL003", "2024-03-15T10:51:00Z",
            "C6062", 1800, 70, 18.4948, -67.1294, "2024-03-15T10:05:00",
            "C6062 BQN SJU", 0.89, SHA64, "fixed_pr_bounds", 0.83, 300.0,
            "approved",
        ),
    ]
    cur.executemany(
        "INSERT INTO screenshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        screenshots,
    )

    # Two flights share a small cell near SJU with >=3 points total, so the
    # Spiderweb bridge emits at least one non-empty POI candidate.
    track_points = [
        (1, "FL001", "2024-03-15T08:00:00", 18.43730, -66.00180, 1000, 35),
        (2, "FL001", "2024-03-15T08:10:00", 18.43760, -66.00210, 1200, 40),
        (3, "FL001", "2024-03-15T08:20:00", 18.43800, -66.00230, 1300, 45),
        (4, "FL002", "2024-03-15T09:00:00", 18.43740, -66.00190, 1000, 30),
        (5, "FL002", "2024-03-15T09:10:00", 18.43790, -66.00240, 1200, 35),
        (6, "FL003", "2024-03-15T10:00:00", 18.49480, -67.12940, 1600, 80),
        (7, "FL003", "2024-03-15T10:15:00", 18.48000, -67.00000, 1700, 85),
    ]
    cur.executemany(
        "INSERT INTO track_points VALUES (?, ?, ?, ?, ?, ?, ?)",
        track_points,
    )

    mission_scores = [
        (
            "FL001", "powerline_inspection", 0.82, None, '{"corridor": 0.75}',
            "Seeded fixture mission inference", "2024-03-15T08:40:00Z",
        ),
        (
            "FL002", "law_enforcement", 0.76, None, '{"recurrence": 0.65}',
            "Seeded fixture mission inference", "2024-03-15T09:45:00Z",
        ),
    ]
    cur.executemany("INSERT INTO mission_scores VALUES (?, ?, ?, ?, ?, ?, ?)", mission_scores)

    alerts = [
        (
            "AL001", "FL001", "N5854Z", "corridor", "MEDIUM", "Seeded corridor alert",
            "Fixture alert used to prove anomaly export against non-empty data.",
            "seeded", "2024-03-15T08:25:00Z", "review", 0, 0, "2024-03-15T08:30:00Z",
        )
    ]
    cur.executemany("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", alerts)
    # Dashboard JSON currently orders alerts by triggered_at while the anomaly
    # schema/export path uses timestamp. Include both so this smoke exercises
    # non-empty dashboard alerts without changing the production exporter here.
    cur.execute("ALTER TABLE alerts ADD COLUMN triggered_at TEXT")
    cur.execute("UPDATE alerts SET triggered_at = timestamp")

    aircraft_profiles = [
        ("N5854Z", "Airbus H125", "PREPA", "powerline_inspection", 0.92, "2024-03-15T08:35:00Z", 1),
        ("N767PD", "Bell 429", "FURA", "law_enforcement", 0.88, "2024-03-15T09:42:00Z", 1),
        ("C6062", "MH-60T", "USCG", "maritime_patrol", 0.9, "2024-03-15T10:50:00Z", 1),
    ]
    cur.executemany("INSERT INTO aircraft_profiles VALUES (?, ?, ?, ?, ?, ?, ?)", aircraft_profiles)

    conn.commit()
    conn.close()


def test_seeded_fixture_exercises_validate_exports_and_dashboard_json(tmp_path):
    db_path = tmp_path / "seeded_flight_database.db"
    _seed_flight_db(db_path)

    validate = _run(["--db", str(db_path), "--validate"])
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "flights" in validate.stdout
    assert "track_points" in validate.stdout
    assert "invalid" in validate.stdout

    pr_intel_dir = tmp_path / "pr_intel"
    pr_export = _run(["--db", str(db_path), "--export-pr-intel", str(pr_intel_dir)])
    assert pr_export.returncode == 0, pr_export.stdout + pr_export.stderr
    report = json.loads((pr_intel_dir / "integration_report.json").read_text())
    assert report["overall_status"] == "PASS"
    assert report["gates"]["schema_validation"] == {"status": "PASS", "records_validated": 6, "invalid": 0}
    assert report["gates"]["coordinate_coverage"]["pct_with_coords"] == 1.0
    assert report["gates"]["evidence_chain_coverage"]["pct_with_screenshot"] == 1.0

    source_manifest = json.loads((pr_intel_dir / "source_manifest.json").read_text())
    row_counts = {f["filename"]: f["record_count"] for f in source_manifest["files"]}
    assert row_counts["airspace_events.parquet"] == 3
    assert row_counts["track_points.parquet"] == 7
    assert row_counts["screenshot_evidence.parquet"] == 3
    assert row_counts["anomaly_index.parquet"] == 1
    assert row_counts["route_lines.geojson"] == 3

    spiderweb_dir = tmp_path / "spiderweb"
    spiderweb_export = _run(["--db", str(db_path), "--export-spiderweb", str(spiderweb_dir)])
    assert spiderweb_export.returncode == 0, spiderweb_export.stdout + spiderweb_export.stderr
    spiderweb_manifest = json.loads((spiderweb_dir / "spiderweb_ingest_manifest.json").read_text())
    spiderweb_counts = {f["filename"]: f["record_count"] for f in spiderweb_manifest["files"]}
    assert spiderweb_counts["airspace_poi_candidates.geojson"] >= 1
    assert spiderweb_counts["airspace_ilap_candidates.geojson"] == 3
    assert spiderweb_counts["aasb_airspace_edges.csv"] == 3

    outputs = tmp_path / "outputs"
    dist = tmp_path / "dist" / "static-dashboard"
    static_export = _run_script([
        "scripts/export_static_dashboard.py",
        "--db", str(db_path),
        "--outputs", str(outputs),
        "--dist", str(dist),
    ])
    assert static_export.returncode == 0, static_export.stdout + static_export.stderr
    dashboard_data = json.loads((outputs / "dashboard_data.json").read_text())
    assert len(dashboard_data["flights"]) == 3
    assert len(dashboard_data["aircraft_profiles"]) == 3
    assert len(dashboard_data["alerts"]) == 1
    assert (dist / "outputs" / "dashboard_data.json").exists()
