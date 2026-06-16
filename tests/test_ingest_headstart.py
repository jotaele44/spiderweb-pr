import csv
import json
from pathlib import Path

from spiderweb.enrichment.headstart_context_enricher import HeadStartContextEnricher
from spiderweb.exports.headstart_context_grid import export_context_grid
from spiderweb.ingestors.ingest_headstart import edge_rows, export_headstart, load_headstart_csv
from spiderweb.schemas.headstart_schema import STANDALONE_CONFIDENCE_CAP


FIXTURE = Path(__file__).parent / "fixtures" / "headstart_sample.csv"


def test_load_headstart_csv_geometry_validity():
    records = load_headstart_csv(FIXTURE)
    assert len(records) == 3
    assert all(17.7 <= r.latitude <= 18.6 for r in records)
    assert all(-67.4 <= r.longitude <= -65.1 for r in records)


def test_operator_dedup_and_edges():
    records = load_headstart_csv(FIXTURE)
    operators = {r.operator_id for r in records}
    assert len(operators) == 2
    edges = edge_rows(records)
    assert len(edges) == 6
    assert {e["edge_type"] for e in edges} == {"OPERATED_BY", "ADMINISTERED_FROM"}


def test_export_headstart_privacy_and_confidence_cap(tmp_path):
    summary = export_headstart(FIXTURE, tmp_path)
    assert summary["records"] == 3
    locations = json.loads((tmp_path / "headstart_locations.geojson").read_text())
    assert locations["metadata"]["precise_points_public"] is False
    for feature in locations["features"]:
        props = feature["properties"]
        assert props["public_export"] == "grid_only"
        assert props["standalone_confidence"] <= STANDALONE_CONFIDENCE_CAP

    with (tmp_path / "headstart_operator_edges.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 6


def test_context_grid_suppresses_precise_points(tmp_path):
    out = tmp_path / "headstart_context_grid.geojson"
    summary = export_context_grid(FIXTURE, out)
    assert summary["records"] == 3
    grid = json.loads(out.read_text())
    assert grid["metadata"]["precise_points_public"] is False
    assert all(f["properties"]["suppression"] == "precise_points_removed" for f in grid["features"])


def test_enrichment_null_handling():
    enricher = HeadStartContextEnricher()
    readiness = enricher.readiness(set())
    assert readiness["status"] == "degraded_pending_external_layers"
    enriched = enricher.enrich_record({"id": "x"})
    assert enriched["id"] == "x"
    assert enriched["enrichment_status"] == "pending_external_layers"
