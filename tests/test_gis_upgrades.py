"""Theme 7 — GIS / export upgrade tests (T7-57/58/59/60/61/65)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from integration.aasb_airspace_bridge import AASBAirspaceBridge
from integration.ilap_airspace_bridge import (
    ILAPAirspaceBridge,
    corridor_activity_label,
)


# ── T7-57 GeoJSON _meta bag ──────────────────────────────────────────────────

def test_ilap_features_carry_meta(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    for fname in (
        "airspace_poi_candidates.geojson",
        "airspace_ilap_candidates.geojson",
        "airspace_corridor_candidates.geojson",
    ):
        data = json.loads((tmp_output / fname).read_text())
        for feat in data.get("features", []):
            meta = feat["properties"].get("_meta")
            assert isinstance(meta, dict), f"{fname}: missing _meta"
            assert set(meta) == {"producer_module", "source_artifact", "produced_at"}
            assert meta["source_artifact"] == fname
            assert meta["producer_module"] == "integration.ilap_airspace_bridge"


def test_ilap_meta_shares_one_timestamp_per_run(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    data = json.loads(
        (tmp_output / "airspace_poi_candidates.geojson").read_text()
    )
    stamps = {f["properties"]["_meta"]["produced_at"] for f in data["features"]}
    assert len(stamps) <= 1, "all features in a run must share one produced_at"


# ── T7-65 CRS / EPSG stamping ────────────────────────────────────────────────

def test_ilap_geojson_has_explicit_epsg(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    data = json.loads(
        (tmp_output / "airspace_poi_candidates.geojson").read_text()
    )
    assert data.get("epsg") == 4326


def test_aasb_manifest_stamps_crs(populated_db, tmp_output):
    AASBAirspaceBridge(populated_db, str(tmp_output)).export_all()
    manifest = json.loads(
        (tmp_output / "spiderweb_ingest_manifest.json").read_text()
    )
    assert manifest.get("crs") == "EPSG:4326"
    assert manifest.get("epsg") == 4326
    for entry in manifest.get("files", []):
        assert entry.get("crs") == "EPSG:4326"
        assert entry.get("epsg") == 4326


# ── T7-59 corridor labels ────────────────────────────────────────────────────

def test_corridor_activity_label_bands():
    assert corridor_activity_label(2) == "LOW"
    assert corridor_activity_label(3) == "MEDIUM"
    assert corridor_activity_label(4) == "MEDIUM"
    assert corridor_activity_label(5) == "HIGH"
    assert corridor_activity_label(20) == "HIGH"


def test_ilap_corridors_have_label(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    data = json.loads(
        (tmp_output / "airspace_corridor_candidates.geojson").read_text()
    )
    for feat in data.get("features", []):
        assert feat["properties"].get("corridor_label") in ("HIGH", "MEDIUM", "LOW")


# ── T7-58 native KML export ──────────────────────────────────────────────────

def test_ilap_writes_kml_siblings(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    for stem in (
        "airspace_poi_candidates",
        "airspace_ilap_candidates",
        "airspace_corridor_candidates",
    ):
        kml = tmp_output / f"{stem}.kml"
        assert kml.exists(), f"missing KML sibling: {kml.name}"
        text = kml.read_text()
        assert text.startswith("<?xml")
        assert "<kml" in text and "</kml>" in text


def test_kml_export_point_and_linestring():
    from integration.kml_export import feature_collection_to_kml

    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-66.1, 18.4]},
                "properties": {"name": "p1", "_meta": {"x": 1}},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-66.1, 18.4], [-66.2, 18.5]],
                },
                "properties": {"corridor_label": "HIGH"},
            },
        ],
    }
    kml = feature_collection_to_kml(fc, "doc")
    assert kml.count("<Placemark>") == 2
    assert "<Point>" in kml and "<LineString>" in kml
    assert "-66.1,18.4" in kml
    # _meta must not leak into ExtendedData
    assert "_meta" not in kml


# ── T7-60 centroid input hook ────────────────────────────────────────────────

def test_load_centroid_csv(tmp_path):
    from integration.mbil import load_centroid_csv

    p = tmp_path / "centroids.csv"
    p.write_text("lat,lon\n18.45,-66.10\n18.01,-66.61\n")
    centroids = load_centroid_csv(str(p))
    assert centroids == [(18.45, -66.10), (18.01, -66.61)]


def test_load_centroid_csv_empty_raises(tmp_path):
    from integration.mbil import load_centroid_csv

    p = tmp_path / "bad.csv"
    p.write_text("lat,lon\n,\nfoo,bar\n")
    with pytest.raises(ValueError):
        load_centroid_csv(str(p))


def test_set_and_reset_municipal_centroids():
    from integration import mbil

    try:
        # A single centroid at San Juan: points far away become MBIL-0.
        mbil.set_municipal_centroids([(18.4655, -66.1057)])
        assert mbil.mbil_class(18.4655, -66.1057) == "MBIL-3"
        # Far southwest corner, still on-island, now far from the lone centroid.
        assert mbil.mbil_class(18.02, -67.15) == "MBIL-0"
    finally:
        mbil.reset_municipal_centroids()
    # After reset the full set is active again (Mayagüez is near a centroid).
    assert mbil.mbil_class(18.4279, -66.7177) in ("MBIL-3", "MBIL-2")


def test_set_empty_centroids_raises():
    from integration import mbil

    with pytest.raises(ValueError):
        mbil.set_municipal_centroids([])


# ── T7-61 QGIS style pack ────────────────────────────────────────────────────

def test_qml_style_pack_present_and_wellformed():
    import xml.dom.minidom as minidom

    styles_dir = Path(__file__).resolve().parents[1] / "styles"
    expected = [
        "airspace_poi_candidates.qml",
        "airspace_corridor_candidates.qml",
        "aasb_airspace_edges.qml",
    ]
    for name in expected:
        path = styles_dir / name
        assert path.exists(), f"missing style: {name}"
        # Parses as XML and is a QGIS qml document.
        doc = minidom.parseString(path.read_text())
        assert doc.documentElement.tagName == "qgis"
