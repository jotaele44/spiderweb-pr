"""Tests for spiderweb/spatial/duckdb_engine.py.

Uses the same tracked municipios fixture as tests/test_geocode_pr.py so the
two engines (hand-rolled ray-casting vs. DuckDB spatial SQL) can be checked
for parity on the same points.
"""

from __future__ import annotations

from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from scripts.geocode_pr import (  # noqa: E402
    municipio_from_point as reference_municipio_from_point,
)
from spiderweb.spatial.duckdb_engine import (  # noqa: E402
    _ALLOWED_PREDICATES,
    municipio_from_point,
    spatial_join,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNI_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "municipios_pr_sample.geojson"

# A point inside the San Juan sample polygon (see MUNI_FIXTURE).
SAN_JUAN_POINT = (18.42, -66.07)
# Well outside Puerto Rico and every sample polygon.
FAR_OUTSIDE_POINT = (10.0, -60.0)


def test_matches_reference_implementation_inside_polygon():
    lat, lon = SAN_JUAN_POINT
    assert (
        municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE)
        == reference_municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE)
        == "San Juan"
    )


def test_matches_reference_implementation_outside_all_polygons():
    lat, lon = FAR_OUTSIDE_POINT
    assert (
        municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE)
        == reference_municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE)
        == ""
    )


def test_missing_file_returns_empty_string(tmp_path):
    assert (
        municipio_from_point(
            18.42, -66.07, municipios_path=tmp_path / "missing.geojson"
        )
        == ""
    )


def test_reuses_supplied_connection():
    con = duckdb.connect(":memory:")
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    try:
        lat, lon = SAN_JUAN_POINT
        assert (
            municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE, con=con)
            == "San Juan"
        )
        # Connection must still be open/usable — municipio_from_point() only
        # closes connections it opened itself.
        assert con.execute("SELECT 1").fetchone() == (1,)
    finally:
        con.close()


def test_spatial_join_self_join_excludes_geometry_column():
    matches = spatial_join(MUNI_FIXTURE, MUNI_FIXTURE, predicate="ST_Intersects")
    for match in matches:
        assert "geom" not in match["left"]
        assert "geom" not in match["right"]
        assert "NAME" in match["left"] and "NAME" in match["right"]


def test_spatial_join_finds_self_intersections():
    # Every polygon trivially intersects itself.
    matches = spatial_join(MUNI_FIXTURE, MUNI_FIXTURE, predicate="ST_Intersects")
    names = {
        m["left"]["NAME"] for m in matches if m["left"]["NAME"] == m["right"]["NAME"]
    }
    assert "San Juan" in names


def test_spatial_join_rejects_unknown_predicate():
    with pytest.raises(ValueError, match="unsupported predicate"):
        spatial_join(MUNI_FIXTURE, MUNI_FIXTURE, predicate="; DROP TABLE x; --")


def test_all_documented_predicates_are_allowed_values():
    # Every entry in the allow-list should be usable without raising — cheap
    # smoke check that the allow-list and the SQL string formatting agree.
    for predicate in _ALLOWED_PREDICATES:
        spatial_join(MUNI_FIXTURE, MUNI_FIXTURE, predicate=predicate)
