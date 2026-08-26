"""
Real-pipeline ingestion for PRIIS.

Maps outputs from the spiderweb-pr CLI backends into priis.db:
  - gis_intelligence.py GeoJSON → sites table
  - earthgpt/ anomaly JSON → anomalies table
  - Finance CSV         → contracts + vendors tables

FR24/ADS-B flight ingestion was retired to docs/legacy/ — airspace ingestion is
owned by skywatcher-pr (see docs/REPO_BOUNDARY.md).

Usage (from repo root):
    python3 server/ingestion/ingest_data.py [--db server/priis.db]
"""

import csv
import json
import sqlite3
import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from server.ingestion.migrations import run_all as run_migrations  # noqa: E402


DB_DEFAULT = Path(__file__).parent.parent / "priis.db"
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ingest_sites_geojson(conn: sqlite3.Connection, geojson_path: Path) -> int:
    """Map gis_intelligence.py GeoJSON output → sites table."""
    if not geojson_path.exists():
        print(f"  [skip] {geojson_path} not found")
        return 0

    with open(geojson_path) as f:
        fc = json.load(f)

    count = 0
    for feat in fc.get("features", []):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        site_id = props.get("id") or props.get("site_id") or f"site-{count}"
        conn.execute(
            """
            INSERT INTO sites (id, name, kind, lat, lng, sensitive, infrastructure_class)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, kind=excluded.kind,
              lat=excluded.lat, lng=excluded.lng,
              sensitive=excluded.sensitive,
              infrastructure_class=excluded.infrastructure_class
            """,
            (
                site_id,
                props.get("name", site_id),
                props.get("kind", "unknown"),
                coords[1],
                coords[0],
                bool(props.get("sensitive", False)),
                props.get("infrastructure_class"),
            ),
        )
        count += 1
    conn.commit()
    return count


def ingest_anomalies_json(conn: sqlite3.Connection, json_path: Path) -> int:
    """Map earthgpt anomaly JSON output → anomalies table."""
    if not json_path.exists():
        print(f"  [skip] {json_path} not found")
        return 0

    with open(json_path) as f:
        records = json.load(f)

    if not isinstance(records, list):
        records = [records]

    count = 0
    for rec in records:
        anomaly_id = rec.get("id") or f"anomaly-{count}"
        conn.execute(
            """
            INSERT INTO anomalies
              (id, title, category, score, band, site_id, summary,
               factors, contracts, event_ids, confidence, contradictions)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              score=excluded.score, band=excluded.band,
              summary=excluded.summary, factors=excluded.factors,
              confidence=excluded.confidence
            """,
            (
                anomaly_id,
                rec.get("title", anomaly_id),
                rec.get("category", "cross-domain"),
                float(rec.get("score", 0.5)),
                rec.get("band", "md"),
                rec.get("site_id") or rec.get("siteId"),
                rec.get("summary", ""),
                json.dumps(rec.get("factors", [])),
                json.dumps(rec.get("contracts", [])),
                json.dumps(rec.get("events", [])),
                int(rec.get("confidence", 2)),
                json.dumps(rec.get("contradictions", [])),
            ),
        )
        count += 1
    conn.commit()
    return count


def ingest_finance_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """Map demo financial CSV → contracts + vendors tables."""
    if not csv_path.exists():
        print(f"  [skip] {csv_path} not found")
        return 0

    count = 0
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vendor_id = row.get("vendor_id", f"v-{count}")
            conn.execute(
                """
                INSERT INTO vendors (id, name, risk, tier)
                VALUES (?,?,?,?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    vendor_id,
                    row.get("vendor_name", vendor_id),
                    float(row.get("risk", 0.0)),
                    row.get("tier", "T2"),
                ),
            )
            contract_id = row.get("contract_id") or f"c-finance-{count}"
            conn.execute(
                """
                INSERT INTO contracts
                  (id, agency, vendor, site, amount, signed, status, tier)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    contract_id,
                    row.get("agency_id", ""),
                    vendor_id,
                    row.get("site_id"),
                    float(row.get("amount", 0)),
                    row.get("signed") or row.get("date", ""),
                    row.get("status", "unknown"),
                    row.get("tier", "T2"),
                ),
            )
            count += 1
    conn.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest real pipeline outputs into priis.db")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Path to priis.db")
    parser.add_argument("--outputs", default=str(OUTPUTS_DIR), help="Pipeline outputs directory")
    args = parser.parse_args()

    outputs = Path(args.outputs)
    conn = _connect(args.db)

    # Ensure the events/alerts schema is up to date before writing.
    run_migrations(conn)

    print("Ingesting sites from GIS GeoJSON...")
    n = ingest_sites_geojson(conn, outputs / "sites.geojson")
    print(f"  {n} sites upserted")

    print("Ingesting anomalies from earthgpt...")
    for fname in ["anomalies.json", "earthgpt_anomalies.json"]:
        p = outputs / fname
        if p.exists():
            n = ingest_anomalies_json(conn, p)
            print(f"  {n} anomalies upserted from {fname}")

    print("Ingesting finance CSV...")
    n = ingest_finance_csv(conn, outputs / "finance.csv")
    print(f"  {n} contracts/vendors inserted")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
