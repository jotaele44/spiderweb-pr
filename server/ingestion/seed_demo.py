#!/usr/bin/env python3
"""Create and populate server/priis.db with an obviously-synthetic demo dataset.

The PRIIS backend (server/backend/main.py) is SQLite-backed and skips startup
migrations when priis.db is missing; several places (scripts/priis_smoke.sh,
server/ingestion/migrations.py, the backend lifespan) expect THIS module to
create the DB and apply the schema. It also backs the offline dashboard export:
scripts/gen_snapshot.py seeds via this module, then dumps the endpoints into
server/frontend/src/lib/snapshot.json.

All rows are clearly-fake demo data (names like "Demo Vendor A", round amounts,
a note marking each record synthetic) — nothing here is a real contract, site,
or record. Coordinates are real Puerto Rico municipality centroids so the map
renders in a sensible place.

Usage (from anywhere):
    python3 server/ingestion/seed_demo.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# server/ingestion/seed_demo.py → parent=ingestion, parent.parent=server
_SERVER = Path(__file__).resolve().parent.parent
DB_PATH = _SERVER / "priis.db"
SCHEMA_PATH = _SERVER / "database" / "schema_sqlite.sql"

# Import the migration helpers whether we're run as a script (cwd on sys.path)
# or imported as server.ingestion.seed_demo.
try:
    from server.ingestion import migrations  # type: ignore
except ImportError:  # pragma: no cover - script-mode fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import migrations  # type: ignore

DEMO_NOTE = "Synthetic demo record — not a real contract/site."

# ─── Demo dataset (deterministic, obviously synthetic) ──────────────────────────

AGENCIES = [
    ("DEMO-AG-1", "DAA", "Demo Agency Alpha"),
    ("DEMO-AG-2", "DAB", "Demo Agency Bravo"),
    ("DEMO-AG-3", "DAC", "Demo Agency Charlie"),
]

VENDORS = [
    ("DEMO-VN-A", "Demo Vendor A", 0.2, "T3"),
    ("DEMO-VN-B", "Demo Vendor B", 0.5, "T2"),
    ("DEMO-VN-C", "Demo Vendor C", 0.8, "T1"),
    ("DEMO-VN-D", "Demo Vendor D", 0.35, "T3"),
]

# (id, name, kind, lat, lng, sensitive, infrastructure_class)
SITES = [
    ("DEMO-ST-1", "Demo Site 1 — San Juan Port",   "port",       18.4655, -66.1057, 1, "maritime"),
    ("DEMO-ST-2", "Demo Site 2 — Ponce Substation", "substation", 18.0111, -66.6141, 0, "power"),
    ("DEMO-ST-3", "Demo Site 3 — Mayaguez Depot",   "depot",      18.2013, -67.1397, 0, "logistics"),
    ("DEMO-ST-4", "Demo Site 4 — Caguas Tower",     "tower",      18.2341, -66.0356, 0, "comms"),
    ("DEMO-ST-5", "Demo Site 5 — Arecibo Airfield", "airfield",   18.4744, -66.7157, 1, "aviation"),
    ("DEMO-ST-6", "Demo Site 6 — Fajardo Marina",   "port",       18.3258, -65.6524, 0, "maritime"),
    ("DEMO-ST-7", "Demo Site 7 — Guayama Plant",    "plant",      17.9841, -66.1136, 1, "industrial"),
    ("DEMO-ST-8", "Demo Site 8 — Aguadilla Hangar", "airfield",   18.4277, -67.1547, 0, "aviation"),
]

# (id, agency, vendor, site, amount, signed, status, tier, procurement_method)
CONTRACTS = [
    ("DEMO-CT-1", "Demo Agency Alpha",   "Demo Vendor A", "DEMO-ST-1", 250000.0, "2025-01-15", "active",   "T3", "open"),
    ("DEMO-CT-2", "Demo Agency Alpha",   "Demo Vendor B", "DEMO-ST-2", 480000.0, "2025-02-03", "active",   "T2", "sole-source"),
    ("DEMO-CT-3", "Demo Agency Bravo",   "Demo Vendor C", "DEMO-ST-5", 1200000.0, "2025-02-20", "review",  "T1", "sole-source"),
    ("DEMO-CT-4", "Demo Agency Bravo",   "Demo Vendor A", "DEMO-ST-3", 90000.0,  "2025-03-11", "closed",  "T4", "open"),
    ("DEMO-CT-5", "Demo Agency Charlie", "Demo Vendor D", "DEMO-ST-7", 620000.0, "2025-03-28", "active",   "T2", "restricted"),
    ("DEMO-CT-6", "Demo Agency Charlie", "Demo Vendor B", "DEMO-ST-4", 150000.0, "2025-04-09", "active",   "T3", "open"),
    ("DEMO-CT-7", "Demo Agency Alpha",   "Demo Vendor C", "DEMO-ST-6", 340000.0, "2025-04-22", "review",   "T2", "open"),
]

# (id, kind, at, site_id, ref_id, label, tier, aircraft fields...)
EVENTS = [
    ("DEMO-EV-1", "filing",   "2025-02-01T14:00:00Z", "DEMO-ST-1", "DEMO-CT-1", "Demo filing near San Juan Port",  "T3",
     None, None, None, None, None, None, None, None, None),
    ("DEMO-EV-2", "sighting", "2025-02-18T09:30:00Z", "DEMO-ST-5", None,        "Demo sighting at Arecibo Airfield", "T2",
     None, None, None, None, None, None, None, None, None),
    ("DEMO-EV-3", "flight",   "2025-03-05T18:45:00Z", "DEMO-ST-5", None,        "Demo flight DEMO123",             "T2",
     "N0DEMO", "DEMO123", "C208", "Demo Air", "TJIG", "TJSJ", 4500, 140, "landed"),
    ("DEMO-EV-4", "flight",   "2025-03-19T21:10:00Z", "DEMO-ST-8", None,        "Demo flight DEMO456",             "T3",
     "N1DEMO", "DEMO456", "BE20", "Demo Air", "TJBQ", "TJIG", 8000, 210, "enroute"),
    ("DEMO-EV-5", "filing",   "2025-04-02T12:00:00Z", "DEMO-ST-7", "DEMO-CT-5", "Demo filing near Guayama Plant",   "T2",
     None, None, None, None, None, None, None, None, None),
]

# (flight_id, ts, at, lat, lng, altitude_ft, speed, direction)
TRACK_POINTS = [
    ("DEMO-EV-3", 1741200000, "2025-03-05T18:40:00Z", 18.34, -66.99, 4500, 140, 95),
    ("DEMO-EV-3", 1741200120, "2025-03-05T18:42:00Z", 18.40, -66.85, 3800, 135, 92),
    ("DEMO-EV-3", 1741200240, "2025-03-05T18:44:00Z", 18.46, -66.72, 1200, 110, 90),
]

# (id, title, category, score, band, site_id, summary, factors, contracts, event_ids, confidence, contradictions)
ANOMALIES = [
    ("DEMO-AN-1", "Demo clustered filings", "temporal", 0.82, "high", "DEMO-ST-1",
     "Synthetic demo anomaly: several demo filings cluster near one site.",
     [{"tag": "burst", "note": "Demo factor"}], ["DEMO-CT-1"], ["DEMO-EV-1"], 3, []),
    ("DEMO-AN-2", "Demo sole-source pattern", "procurement", 0.67, "medium", "DEMO-ST-5",
     "Synthetic demo anomaly: repeated sole-source demo awards.",
     [{"tag": "sole-source", "note": "Demo factor"}], ["DEMO-CT-3"], [], 2, ["Demo contradiction note"]),
    ("DEMO-AN-3", "Demo flight proximity", "spatial", 0.54, "medium", "DEMO-ST-8",
     "Synthetic demo anomaly: demo flight passes near a sensitive demo site.",
     [{"tag": "proximity", "note": "Demo factor"}], [], ["DEMO-EV-4"], 2, []),
    ("DEMO-AN-4", "Demo low-signal note", "misc", 0.31, "low", None,
     "Synthetic demo anomaly with low score.", [], [], [], 1, []),
]

SOURCES = [
    ("DEMO-SRC-1", "Demo Registry Feed",   "T2", "registry", "online"),
    ("DEMO-SRC-2", "Demo ADS-B Archive",   "T3", "adsb",     "online"),
    ("DEMO-SRC-3", "Demo Filings Portal",  "T3", "filings",  "degraded"),
    ("DEMO-SRC-4", "Demo Imagery Provider","T1", "imagery",  "offline"),
    ("DEMO-SRC-5", "Demo OSINT Stream",    "T4", "osint",    "online"),
]

INVESTIGATIONS = [
    ("DEMO-INV-1", "Demo investigation — port activity", "spatial", "active"),
    ("DEMO-INV-2", "Demo investigation — procurement",   "procurement", "active"),
]

ALERTS = [
    ("DEMO-AL-1", "2025-03-05T18:46:00Z", "aircraft", "Demo watchlist aircraft seen", "T2", "DEMO-INV-1", "N0DEMO"),
    ("DEMO-AL-2", "2025-04-02T12:05:00Z", "filing",   "Demo filing threshold crossed", "T3", "DEMO-INV-2", None),
]

_TABLES = ["alerts", "investigations", "sources", "anomalies", "track_points",
           "events", "contracts", "sites", "vendors", "agencies"]


def _seed(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for t in _TABLES:
        cur.execute(f"DELETE FROM {t}")

    cur.executemany("INSERT INTO agencies (id, code, name) VALUES (?,?,?)", AGENCIES)
    cur.executemany("INSERT INTO vendors (id, name, risk, tier) VALUES (?,?,?,?)", VENDORS)
    cur.executemany(
        "INSERT INTO sites (id, name, kind, lat, lng, sensitive, infrastructure_class) "
        "VALUES (?,?,?,?,?,?,?)", SITES,
    )
    cur.executemany(
        "INSERT INTO contracts (id, agency, vendor, site, amount, signed, status, tier, "
        "procurement_method, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(*c, DEMO_NOTE) for c in CONTRACTS],
    )
    cur.executemany(
        "INSERT INTO events (id, kind, at, site_id, ref_id, label, tier, registration, "
        "callsign, aircraft_type, operator, origin_code, destination_code, altitude_ft, "
        "ground_speed_mph, flight_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        EVENTS,
    )
    cur.executemany(
        "INSERT INTO track_points (flight_id, ts, at, lat, lng, altitude_ft, speed, direction) "
        "VALUES (?,?,?,?,?,?,?,?)", TRACK_POINTS,
    )
    cur.executemany(
        "INSERT INTO anomalies (id, title, category, score, band, site_id, summary, factors, "
        "contracts, event_ids, confidence, contradictions) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (a[0], a[1], a[2], a[3], a[4], a[5], a[6],
             json.dumps(a[7]), json.dumps(a[8]), json.dumps(a[9]), a[10], json.dumps(a[11]))
            for a in ANOMALIES
        ],
    )
    cur.executemany("INSERT INTO sources (id, name, tier, kind, status) VALUES (?,?,?,?,?)", SOURCES)
    cur.executemany(
        "INSERT INTO investigations (id, title, active_vector, status) VALUES (?,?,?,?)",
        INVESTIGATIONS,
    )
    cur.executemany(
        "INSERT INTO alerts (id, at, kind, title, tier, investigation, registration) "
        "VALUES (?,?,?,?,?,?,?)", ALERTS,
    )
    conn.commit()


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrations.run_all(conn)
        _seed(conn)
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES
        }
    finally:
        conn.close()
    print(f"seeded {DB_PATH}  {counts}")


if __name__ == "__main__":
    main()
