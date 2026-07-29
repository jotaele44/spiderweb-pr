"""Contract tests for the canonical desktop/frontend GIS runtime boundary."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.backend import main
from server.backend.gis_app import app

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = REPO_ROOT / "server" / "database" / "schema_sqlite.sql"


@pytest.fixture()
def gis_client(tmp_path, monkeypatch):
    database = tmp_path / "gis-boundary.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO sources (
                id, name, tier, kind, status, publisher, url, captured_at,
                hash, lineage, provenance_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SRC-GIS",
                "Municipal source",
                "T1",
                "registry",
                "online",
                "Publisher",
                "https://example.test/municipal",
                "2026-07-20T12:30:00Z",
                "source-hash",
                json.dumps([{"actor": "registry", "step": "capture"}]),
                "Authoritative municipal feed",
            ),
        )
        connection.execute(
            "INSERT INTO sources (id, name, tier, kind, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("SRC-AIR", "Air archive", "T2", "fr24", "online"),
        )
        connection.execute(
            """
            INSERT INTO sites (
                id, name, kind, lat, lng, sensitive, source_ids, lineage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SITE-1",
                "Municipal site",
                "reservoir",
                18.3,
                -66.1,
                0,
                json.dumps(["SRC-GIS"]),
                json.dumps([{"actor": "site-normalizer", "step": "normalize"}]),
            ),
        )
        connection.execute(
            """
            INSERT INTO events (
                id, kind, at, site_id, label, tier, source_ids, lineage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "EVENT-GIS",
                "imagery",
                "2026-07-20T12:45:00Z",
                "SITE-1",
                "Observed shoreline change",
                "T1",
                json.dumps(["SRC-GIS"]),
                json.dumps([{"actor": "imagery-adapter", "step": "observe"}]),
            ),
        )
        connection.execute(
            """
            INSERT INTO events (
                id, kind, at, site_id, label, tier, registration, callsign,
                source_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "EVENT-AIR",
                "flight",
                "2026-07-20T13:00:00Z",
                "SITE-1",
                "Excluded fixture",
                "T2",
                "N00000",
                "TEST123",
                json.dumps(["SRC-AIR"]),
            ),
        )
        connection.execute(
            """
            INSERT INTO anomalies (
                id, title, category, score, band, site_id, summary, factors,
                contracts, event_ids, confidence, contradictions, source_ids,
                lineage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ANOMALY-GIS",
                "Spatial change",
                "spatial",
                0.8,
                "high",
                "SITE-1",
                "Spatial fixture",
                "[]",
                "[]",
                json.dumps(["EVENT-GIS"]),
                3,
                "[]",
                json.dumps(["SRC-GIS"]),
                json.dumps([{"actor": "anomaly-engine", "step": "score"}]),
            ),
        )
        connection.execute(
            """
            INSERT INTO anomalies (
                id, title, category, score, band, site_id, summary, factors,
                contracts, event_ids, confidence, contradictions, source_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ANOMALY-AIR",
                "Excluded linked fixture",
                "spatial",
                0.5,
                "medium",
                "SITE-1",
                "Linked to excluded event",
                "[]",
                "[]",
                json.dumps(["EVENT-AIR"]),
                2,
                "[]",
                json.dumps(["SRC-AIR"]),
            ),
        )
        connection.commit()

    monkeypatch.setattr(main, "DB_PATH", database)
    with TestClient(app) as client:
        yield client


def test_runtime_exposes_only_gis_routes():
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/catalog" in paths
    assert "/geo/{layer}.geojson" in paths
    assert "/events/{flight_id}/track" not in paths
    assert "/pipeline/run" not in paths
    assert "/rag/query" not in paths


def test_real_catalog_has_no_flight_content(gis_client):
    response = gis_client.get("/catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert all(
        family.get("id") != "flight_activity" and family.get("domain") != "flights"
        for family in catalog["families"]
    )
    assert all(
        layer["layer_id"] != "flights"
        for family in catalog["families"]
        for layer in family["layers"]
    )


def test_flight_fixture_and_linked_records_are_rejected(gis_client):
    events = gis_client.get("/events").json()
    assert [record["id"] for record in events] == ["EVENT-GIS"]
    assert not {
        "registration",
        "callsign",
        "aircraftType",
        "originCode",
        "destinationCode",
    }.intersection(events[0])

    anomalies = gis_client.get("/anomalies").json()
    assert [record["id"] for record in anomalies] == ["ANOMALY-GIS"]
    sources = gis_client.get("/sources").json()
    assert [record["id"] for record in sources] == ["SRC-GIS"]
    assert gis_client.get("/geo/flights.geojson").status_code == 400


def test_provenance_roundtrip_preserves_ids_url_capture_hash_and_lineage(gis_client):
    site = gis_client.get("/sites").json()[0]
    event = gis_client.get("/events").json()[0]
    anomaly = gis_client.get("/anomalies").json()[0]
    source = gis_client.get("/sources").json()[0]

    assert site["sourceIds"] == ["SRC-GIS"]
    assert event["sourceIds"] == ["SRC-GIS"]
    assert anomaly["sourceIds"] == ["SRC-GIS"]
    assert event["lineage"] == [{"actor": "imagery-adapter", "step": "observe"}]
    assert source["url"] == "https://example.test/municipal"
    assert source["capturedAt"] == "2026-07-20T12:30:00Z"
    assert source["hash"] == "source-hash"
    assert source["lineage"] == [{"actor": "registry", "step": "capture"}]


def test_catalog_provenance_includes_manifest_lineage(gis_client):
    catalog = gis_client.get("/catalog").json()
    municipios = next(
        layer
        for family in catalog["families"]
        for layer in family["layers"]
        if layer["layer_id"] == "municipios"
    )
    provenance = municipios["provenance"]
    assert provenance["source_ids"]
    assert provenance["url"]
    assert provenance["captured_at"]
    assert provenance["hash"]
    assert provenance["lineage"]
