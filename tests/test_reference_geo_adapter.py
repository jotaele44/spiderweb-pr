"""Offline unit tests for server/ingestion/ingest_reference_geo.py.

The live fetchers (NID CSV, GNIS S3 zip, NWI ArcGIS service) are exercised only
under the ``integration`` marker; the default suite covers the pure helpers and
the source contract with no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server" / "ingestion"))

import ingest_reference_geo as m  # noqa: E402


def test_sources_cover_the_three_reference_layers():
    assert set(m.SOURCES) == {"nid", "gnis", "nwi"}
    assert m.SOURCES["nid"]["layer"] == "nid_dams"
    assert m.SOURCES["gnis"]["layer"] == "gazetteer_pr_domestic_names"
    assert m.SOURCES["nwi"]["layer"] == "wetlands_nwi_prvi"
    assert m.SOURCES["nwi"]["geometry"] == "polygon"
    for spec in m.SOURCES.values():
        assert callable(spec["fetch"])


def test_in_pr_bbox():
    assert m._in_pr(18.4, -66.1) is True
    assert m._in_pr(18.4, -66.1) and not m._in_pr(-66.1, 18.4)  # swapped → outside
    assert m._in_pr(40.0, -100.0) is False  # way off
    assert m._in_pr(0.0, 0.0) is False


def test_round_geometry_recurses_and_rounds():
    geom = {"type": "Polygon", "coordinates": [[[-66.123456789, 18.987654321], [-66.1, 18.9]]]}
    out = m._round_geometry(geom, 5)
    assert out["coordinates"][0][0] == [-66.12346, 18.98765]
    # non-coordinate scalars pass through untouched
    assert m._round_geometry("PEM1A") == "PEM1A"


def test_point_feature_strips_empty_and_rounds():
    feat = m._point_feature(-66.1234567, 18.7654321, {"name": "X", "blank": "", "none": None, "n": 3})
    assert feat["geometry"]["type"] == "Point"
    assert feat["geometry"]["coordinates"] == [-66.123457, 18.765432]
    # empty/None properties dropped; real ones kept
    assert feat["properties"] == {"name": "X", "n": 3}


def test_build_parser_defaults():
    args = m.build_parser().parse_args([])
    assert args.source == "all"
    assert args.dry_run is False


def _poly(oid, wtype):
    return {
        "type": "Feature",
        "properties": {
            "Wetlands.OBJECTID": oid, "Wetlands.ATTRIBUTE": "X",
            "Wetlands.WETLAND_TYPE": wtype, "Wetlands.ACRES": 1.0,
        },
        "geometry": {"type": "Polygon", "coordinates": [
            [[-66.1, 18.4], [-66.09, 18.4], [-66.09, 18.41], [-66.1, 18.41], [-66.1, 18.4]]
        ]},
    }


def test_simplify_polygon_rounds_and_drops_degenerate():
    geom = {"type": "Polygon", "coordinates": [
        [[-66.123456, 18.987654], [-66.09, 18.4], [-66.09, 18.41], [-66.123456, 18.987654]]
    ]}
    out = m._simplify_polygon(geom, 0.0001)
    assert out is None or out["type"] == "Polygon"
    # tol<=0 → plain rounding, geometry preserved
    rounded = m._simplify_polygon(geom, 0)
    assert rounded["coordinates"][0][0] == [-66.12346, 18.98765]
    assert m._simplify_polygon(None, 0.0001) is None


def test_fetch_nwi_drops_deepwater_by_default(monkeypatch):
    def fake_query(cell, offset, timeout):
        return [_poly(1, "Freshwater Emergent Wetland"),
                _poly(2, m.NWI_DEEPWATER_TYPE)] if offset == 0 else []
    monkeypatch.setattr(m, "_nwi_query", fake_query)

    feats, meta = m.fetch_nwi(Path("/tmp"), timeout=1, tile_deg=0.1,
                              bbox=(-66.1, -66.0, 18.4, 18.5))
    assert [f["properties"]["objectid"] for f in feats] == [1]  # deepwater dropped
    assert meta["dropped_deepwater"] == 1
    assert meta["include_deepwater"] is False

    feats2, meta2 = m.fetch_nwi(Path("/tmp"), timeout=1, include_deepwater=True,
                                tile_deg=0.1, bbox=(-66.1, -66.0, 18.4, 18.5))
    assert {f["properties"]["objectid"] for f in feats2} == {1, 2}
    assert meta2["dropped_deepwater"] == 0


@pytest.mark.integration
def test_nid_fetch_live(tmp_path):
    feats, meta = m.fetch_nid(tmp_path, timeout=200)
    assert len(feats) > 0
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        assert m._in_pr(lat, lon)
    assert meta["sha256"] and meta["bytes"] > 0


@pytest.mark.integration
def test_gnis_fetch_live(tmp_path):
    feats, meta = m.fetch_gnis(tmp_path, timeout=120)
    assert len(feats) > 0
    assert all("name" in f["properties"] for f in feats)
