"""Tests for spiderweb/spatial/duckdb_engine.py.

Uses the same tracked municipios fixture as tests/test_geocode_pr.py so the
two engines (hand-rolled ray-casting vs. DuckDB spatial SQL) can be checked
for parity on the same points when a local spatial-extension bundle is
available. Unit gates always verify that runtime installation is disabled.
"""

from __future__ import annotations

from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from scripts.geocode_pr import (  # noqa: E402
    municipio_from_point as reference_municipio_from_point,
)
from spiderweb.spatial import duckdb_engine  # noqa: E402
from spiderweb.spatial.duckdb_engine import (  # noqa: E402
    _ALLOWED_PREDICATES,
    SpatialExtensionUnavailable,
    connect,
    municipio_from_point,
    spatial_join,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNI_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "municipios_pr_sample.geojson"

# A point inside the San Juan sample polygon (see MUNI_FIXTURE).
SAN_JUAN_POINT = (18.42, -66.07)
# Well outside Puerto Rico and every sample polygon.
FAR_OUTSIDE_POINT = (10.0, -60.0)


class _FakeConnection:
    def __init__(self, *, load_error: Exception | None = None):
        self.calls: list[tuple[str, str]] = []
        self.closed = False
        self.load_error = load_error

    def execute(self, statement: str):
        self.calls.append(("execute", statement))
        return self

    def load_extension(self, locator: str) -> None:
        self.calls.append(("load_extension", locator))
        if self.load_error is not None:
            raise self.load_error

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def spatial_con():
    try:
        con = connect()
    except SpatialExtensionUnavailable as exc:
        pytest.skip(f"local DuckDB spatial extension not staged: {exc}")
    try:
        yield con
    finally:
        con.close()


def test_connect_disables_extension_network_before_load(monkeypatch):
    fake = _FakeConnection()
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)

    assert connect() is fake
    assert fake.calls == [
        ("execute", "SET autoinstall_known_extensions = false"),
        ("execute", "SET autoload_known_extensions = false"),
        ("load_extension", "spatial"),
    ]
    assert not any("INSTALL" in statement.upper() for _, statement in fake.calls)


def test_connect_loads_explicit_local_extension(monkeypatch, tmp_path):
    extension = tmp_path / "spatial.duckdb_extension"
    extension.write_bytes(b"fixture")
    fake = _FakeConnection()
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)

    assert connect(extension_path=extension) is fake
    assert fake.calls[-1] == ("load_extension", str(extension.resolve()))


def test_connect_closes_and_fails_when_local_extension_is_unavailable(monkeypatch):
    fake = _FakeConnection(load_error=RuntimeError("not installed"))
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)

    with pytest.raises(SpatialExtensionUnavailable, match="runtime installation is prohibited"):
        connect()
    assert fake.closed is True


def test_missing_configured_extension_fails_before_open(monkeypatch, tmp_path):
    def unexpected_connect(_):
        raise AssertionError("duckdb.connect must not run for a missing configured file")

    monkeypatch.setattr(duckdb_engine.duckdb, "connect", unexpected_connect)
    with pytest.raises(SpatialExtensionUnavailable, match="does not exist"):
        connect(extension_path=tmp_path / "missing.duckdb_extension")


def test_matches_reference_implementation_inside_polygon(spatial_con):
    lat, lon = SAN_JUAN_POINT
    assert (
        municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE, con=spatial_con)
        == reference_municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE)
        == "San Juan"
    )


def test_matches_reference_implementation_outside_all_polygons(spatial_con):
    lat, lon = FAR_OUTSIDE_POINT
    assert (
        municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE, con=spatial_con)
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


def test_reuses_supplied_connection(spatial_con):
    lat, lon = SAN_JUAN_POINT
    assert (
        municipio_from_point(lat, lon, municipios_path=MUNI_FIXTURE, con=spatial_con)
        == "San Juan"
    )
    # Connection must still be open/usable — municipio_from_point() only
    # closes connections it opened itself.
    assert spatial_con.execute("SELECT 1").fetchone() == (1,)


def test_spatial_join_self_join_excludes_geometry_column(spatial_con):
    matches = spatial_join(
        MUNI_FIXTURE,
        MUNI_FIXTURE,
        predicate="ST_Intersects",
        con=spatial_con,
    )
    for match in matches:
        assert "geom" not in match["left"]
        assert "geom" not in match["right"]
        assert "NAME" in match["left"] and "NAME" in match["right"]


def test_spatial_join_finds_self_intersections(spatial_con):
    # Every polygon trivially intersects itself.
    matches = spatial_join(
        MUNI_FIXTURE,
        MUNI_FIXTURE,
        predicate="ST_Intersects",
        con=spatial_con,
    )
    names = {
        match["left"]["NAME"]
        for match in matches
        if match["left"]["NAME"] == match["right"]["NAME"]
    }
    assert "San Juan" in names


def test_spatial_join_rejects_unknown_predicate():
    with pytest.raises(ValueError, match="unsupported predicate"):
        spatial_join(MUNI_FIXTURE, MUNI_FIXTURE, predicate="; DROP TABLE x; --")


def test_all_documented_predicates_are_allowed_values(spatial_con):
    # Every entry in the allow-list should be usable without raising when the
    # certified local extension bytes are staged.
    for predicate in _ALLOWED_PREDICATES:
        spatial_join(MUNI_FIXTURE, MUNI_FIXTURE, predicate=predicate, con=spatial_con)
