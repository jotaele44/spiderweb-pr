"""ADS-B per-tail archive ingest: parsing, events + track_points, dedup, migration."""

import io
import sqlite3
import zipfile
from pathlib import Path

from scripts.parse_adsb_archive import iter_flight_csvs, parse_flight
from server.ingestion.ingest_data import ingest_fr24_csv, ingest_track_points
from server.ingestion.migrations import ensure_track_points_table, run_all

SCHEMA = Path(__file__).resolve().parents[1] / "server" / "database" / "schema_sqlite.sql"

SAMPLE_CSV = (
    "Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction\n"
    "1749231491,2025-06-06T17:38:11Z,N79036,\"19.754396,-70.564735\",0,0,270\n"
    "1749231888,2025-06-06T17:44:48Z,N79036,\"19.7,-70.5\",1200,90,284\n"
    "1749231935,2025-06-06T17:45:35Z,N79036,\"19.8,-70.6\",500,30,357\n"
)


def _fresh_db(tmp_path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "priis.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    return conn


def test_parse_flight_builds_event_and_points():
    event, points = parse_flight("3aadc81d", SAMPLE_CSV)

    assert event["id"] == "adsb-3aadc81d"
    assert event["registration"] == "N79036"
    assert event["callsign"] == "N79036"
    assert event["at"] == "2025-06-06T17:38:11Z"
    assert event["origin_code"] == "19.754396,-70.564735"
    assert event["destination_code"] == "19.8,-70.6"
    assert event["altitude_ft"] == 1200  # peak altitude
    assert event["ground_speed_mph"] == 90  # peak speed
    assert event["flight_status"] == "3 ADS-B points"

    assert len(points) == 3
    assert points[0] == {
        "flight_id": "adsb-3aadc81d", "ts": 1749231491,
        "at": "2025-06-06T17:38:11Z", "lat": 19.754396, "lng": -70.564735,
        "altitude_ft": 0, "speed": 0, "direction": 270,
    }


def test_known_aircraft_enrichment():
    csv_text = SAMPLE_CSV.replace("N79036", "N413LP")
    event, _ = parse_flight("3955f1c2", csv_text)
    assert event["aircraft_type"] == "Eurocopter AS350 B3"
    assert event["operator"] == "CAMAPE SE"


def test_ensure_track_points_table_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "priis.db")
    # First call on an empty DB creates the table.
    assert ensure_track_points_table(conn) is True
    # Second call is a no-op (table already present).
    assert ensure_track_points_table(conn) is False
    # run_all is also safe to call repeatedly.
    run_all(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(track_points)")}
    assert {"flight_id", "ts", "lat", "lng", "altitude_ft", "speed", "direction"} <= cols


def test_end_to_end_ingest_and_dedup(tmp_path):
    conn = _fresh_db(tmp_path)
    event, points = parse_flight("3aadc81d", SAMPLE_CSV)

    # Write the events CSV the way the script does, then ingest both layers.
    import csv as _csv
    from scripts.parse_adsb_archive import EVENT_CSV_FIELDS
    csv_path = tmp_path / "events.csv"
    with csv_path.open("w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=EVENT_CSV_FIELDS)
        w.writeheader()
        w.writerow(event)

    assert ingest_fr24_csv(conn, csv_path) == 1
    assert ingest_track_points(conn, points) == 3

    # Re-ingesting the same flight is idempotent: no duplicate event or points.
    ingest_fr24_csv(conn, csv_path)
    assert ingest_track_points(conn, points) == 0
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM track_points WHERE flight_id='adsb-3aadc81d'"
    ).fetchone()[0] == 3


def _zip_bytes(files: dict[str, str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    buf.seek(0)
    return buf


def test_iter_dedupes_nested_zip_duplicates(tmp_path):
    """A wrapper zip re-bundling the same flight id must yield it only once."""
    inner = _zip_bytes({"3aadc81d.csv": SAMPLE_CSV}).getvalue()
    archive = tmp_path / "Archive.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("3aadc81d.csv", SAMPLE_CSV)          # top-level copy
        zf.writestr("__MACOSX/._3aadc81d.csv", "junk")   # resource fork (ignored)
        zf.writestr("wrapper.zip", inner)                # nested duplicate

    flights = list(iter_flight_csvs(archive))
    assert len(flights) == 1
    assert flights[0][0] == "3aadc81d"
