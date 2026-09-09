"""Tests for spiderweb/spatial/duckdb_engine.py.

Uses the same tracked municipios fixture as tests/test_geocode_pr.py so the
two engines (hand-rolled ray-casting vs. DuckDB spatial SQL) can be checked
for parity on the same points when a local spatial-extension bundle is
available. Unit gates always verify that runtime installation is disabled.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from scripts.geocode_pr import (  # noqa: E402
    municipio_from_point as reference_municipio_from_point,
)
from spiderweb.spatial import duckdb_engine  # noqa: E402
from spiderweb.spatial.duckdb_engine import (  # noqa: E402
    _ALLOWED_PREDICATES,
    AmbiguousMunicipioError,
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


def test_connect_uses_environment_file_and_explicit_path_takes_precedence(
    monkeypatch, tmp_path
):
    configured = tmp_path / "configured.duckdb_extension"
    explicit = tmp_path / "explicit.duckdb_extension"
    for path in (configured, explicit):
        path.write_bytes(b"fixture")
    monkeypatch.setenv(duckdb_engine.SPATIAL_EXTENSION_ENV, str(configured))
    fake = _FakeConnection()
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)
    connect()
    assert fake.calls[-1] == ("load_extension", str(configured))
    connect(extension_path=explicit)
    assert fake.calls[-1] == ("load_extension", str(explicit))
    with pytest.raises(SpatialExtensionUnavailable):
        connect(extension_path="")


def test_setting_failure_closes_connection_without_loading(monkeypatch):
    monkeypatch.delenv(duckdb_engine.SPATIAL_EXTENSION_ENV, raising=False)
    fake = _FakeConnection()

    def fail_setting(_):
        raise RuntimeError("unsupported setting")

    fake.execute = fail_setting
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)
    with pytest.raises(SpatialExtensionUnavailable):
        connect()
    assert fake.closed
    assert fake.calls == []


@pytest.fixture
def spatial_con():
    try:
        con = connect()
    except SpatialExtensionUnavailable as exc:
        if os.environ.get(duckdb_engine.SPATIAL_EXTENSION_ENV) is not None:
            pytest.fail(
                f"Configured spatial extension failed to load: {exc.__cause__ or exc}"
            )
        pytest.skip(f"local DuckDB spatial extension not staged: {exc}")
    try:
        yield con
    finally:
        con.close()


def test_connect_disables_extension_network_before_load(monkeypatch):
    monkeypatch.delenv(duckdb_engine.SPATIAL_EXTENSION_ENV, raising=False)
    fake = _FakeConnection()
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)

    assert connect() is fake
    assert fake.calls == [
        ("execute", "SET autoinstall_known_extensions = false"),
        ("execute", "SET autoload_known_extensions = false"),
        ("load_extension", "spatial"),
    ]
    # Word-boundary match: an `INSTALL <ext>` statement, not the unrelated
    # `autoinstall_known_extensions` setting name (which also contains the
    # substring "INSTALL" and would otherwise false-positive here).
    assert not any(
        re.search(r"\bINSTALL\b", statement, re.IGNORECASE)
        for _, statement in fake.calls
    )


def test_connect_loads_explicit_local_extension(monkeypatch, tmp_path):
    extension = tmp_path / "spatial.duckdb_extension"
    extension.write_bytes(b"fixture")
    fake = _FakeConnection()
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)

    assert connect(extension_path=extension) is fake
    assert fake.calls[-1] == ("load_extension", str(extension.resolve()))


def test_connect_closes_and_fails_when_local_extension_is_unavailable(monkeypatch):
    monkeypatch.delenv(duckdb_engine.SPATIAL_EXTENSION_ENV, raising=False)
    fake = _FakeConnection(load_error=RuntimeError("not installed"))
    monkeypatch.setattr(duckdb_engine.duckdb, "connect", lambda _: fake)

    with pytest.raises(
        SpatialExtensionUnavailable, match="runtime installation is prohibited"
    ):
        connect()
    assert fake.closed is True


def test_missing_configured_extension_fails_before_open(monkeypatch, tmp_path):
    def unexpected_connect(_):
        raise AssertionError(
            "duckdb.connect must not run for a missing configured file"
        )

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


@pytest.mark.parametrize("reverse", [False, True])
def test_overlapping_rows_remain_unresolved_even_with_identical_names(
    spatial_con, tmp_path, reverse
):
    source = json.loads(MUNI_FIXTURE.read_text())
    first = source["features"][0]
    second = deepcopy(first)
    second["properties"]["GEOID"] = "distinct-source-id"
    rows = [first, second]
    source["features"] = list(reversed(rows)) if reverse else rows
    path = tmp_path / "overlap.geojson"
    path.write_text(json.dumps(source))
    with pytest.raises(AmbiguousMunicipioError) as caught:
        municipio_from_point(*SAN_JUAN_POINT, municipios_path=path, con=spatial_con)
    candidates = caught.value.candidates
    assert len(candidates) == 2
    assert {row["GEOID"] for row in candidates} == {"72127", "distinct-source-id"}
    assert all(row["NAME"] == "San Juan" and row["geom"] for row in candidates)
    assert spatial_con.execute("SELECT 1").fetchone() == (1,)


@pytest.mark.parametrize("name", [None, "", "   "])
def test_containing_row_requires_nonempty_name(spatial_con, tmp_path, name):
    source = json.loads(MUNI_FIXTURE.read_text())
    source["features"][0]["properties"]["NAME"] = name
    path = tmp_path / "invalid-name.geojson"
    path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="nonempty string NAME"):
        municipio_from_point(*SAN_JUAN_POINT, municipios_path=path, con=spatial_con)


def test_unique_source_label_preserves_raw_spacing_and_accents(spatial_con, tmp_path):
    source = json.loads(MUNI_FIXTURE.read_text())
    source["features"][0]["properties"]["NAME"] = "  Sán  Juãn  "
    path = tmp_path / "raw-name.geojson"
    path.write_text(json.dumps(source))
    assert (
        municipio_from_point(*SAN_JUAN_POINT, municipios_path=path, con=spatial_con)
        == "  Sán  Juãn  "
    )


@pytest.mark.parametrize(
    "point", [(float("nan"), 0), (0, float("inf")), (91, 0), (0, -181)]
)
def test_invalid_coordinates_fail_even_when_source_is_missing(tmp_path, point):
    with pytest.raises(ValueError):
        municipio_from_point(*point, municipios_path=tmp_path / "missing.geojson")


def test_polygon_boundary_is_not_an_interior_match(spatial_con):
    assert (
        municipio_from_point(
            18.42, -66.0991, municipios_path=MUNI_FIXTURE, con=spatial_con
        )
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
