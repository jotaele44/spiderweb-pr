"""DuckDB-backed embedded spatial SQL engine for ad hoc GeoJSON queries.

WHY THIS EXISTS
----------------
``scripts/geocode_pr.py`` hand-rolls a dependency-free ray-casting
point-in-polygon for its one fixed, hot call site (harvester reverse-geocode
against ``data/municipios.geojson``). That stays stdlib-only by design — it
is not being replaced here.

This module is an additive, opt-in alternative for everything *beyond* that
one case: ad hoc spatial joins and predicate queries across whatever GeoJSON
artifacts already exist on disk (municipios, TIGER layers, gazetteer output,
...), expressed as SQL instead of a new hand-rolled geometry loop each time.

WHY DUCKDB, NOT SPARK/SEDONA/WHEROBOTS
---------------------------------------
Every dataset spiderweb-pr processes is Puerto-Rico-scoped and megabytes in
size (see RECOMMENDATIONS.md — no documented scaling bottleneck exists
anywhere in this repo). An embedded, dependency-light SQL engine is the right
amount of tooling for that: no cluster, no external service, no new
operational surface. Reach for something heavier only if a producer starts
ingesting data that no longer fits single-machine memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MUNICIPIOS = REPO_ROOT / "data" / "municipios.geojson"

# DuckDB spatial's binary predicate functions. Kept as an explicit allow-list
# so `predicate` can never be used to inject arbitrary SQL into spatial_join.
_ALLOWED_PREDICATES = {
    "ST_Intersects",
    "ST_Contains",
    "ST_Within",
    "ST_Touches",
    "ST_Crosses",
    "ST_Overlaps",
}


def connect() -> "duckdb.DuckDBPyConnection":
    """Open an in-memory DuckDB connection with the `spatial` extension loaded."""
    con = duckdb.connect(":memory:")
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    return con


def municipio_from_point(
    lat: float,
    lon: float,
    *,
    municipios_path: Path = DEFAULT_MUNICIPIOS,
    con: Optional["duckdb.DuckDBPyConnection"] = None,
) -> str:
    """Point-in-polygon reverse geocode against a municipios GeoJSON, via a
    single DuckDB spatial SQL query.

    Same contract as ``scripts.geocode_pr.municipio_from_point``: returns the
    ``NAME`` property of the containing polygon, or ``""`` if the point falls
    outside every polygon or the municipios file doesn't exist.
    """
    if not municipios_path.exists():
        return ""
    owns_con = con is None
    con = con or connect()
    try:
        row = con.execute(
            """
            SELECT NAME
            FROM ST_Read(?)
            WHERE ST_Contains(geom, ST_Point(?, ?))
            LIMIT 1
            """,
            [str(municipios_path), lon, lat],
        ).fetchone()
        return row[0] if row else ""
    finally:
        if owns_con:
            con.close()


def _columns(con: "duckdb.DuckDBPyConnection", path: Path) -> list[str]:
    described = con.execute("SELECT * FROM ST_Read(?) LIMIT 0", [str(path)]).description
    return [name for name, *_ in described if name != "geom"]


def spatial_join(
    left_path: Path,
    right_path: Path,
    *,
    predicate: str = "ST_Intersects",
    con: Optional["duckdb.DuckDBPyConnection"] = None,
) -> list[dict]:
    """Spatial-join two GeoJSON files on a geometry predicate (default:
    intersects) and return the matched (left, right) property pairs.

    ``predicate`` must be one of DuckDB spatial's binary predicate functions
    (see ``_ALLOWED_PREDICATES``); anything else raises ``ValueError`` rather
    than being interpolated into SQL.
    """
    if predicate not in _ALLOWED_PREDICATES:
        raise ValueError(
            f"unsupported predicate: {predicate!r} "
            f"(expected one of {sorted(_ALLOWED_PREDICATES)})"
        )
    owns_con = con is None
    con = con or connect()
    try:
        left_cols = _columns(con, left_path)
        right_cols = _columns(con, right_path)
        rows = con.execute(
            f"""
            SELECT l.* EXCLUDE (geom), r.* EXCLUDE (geom)
            FROM ST_Read(?) AS l, ST_Read(?) AS r
            WHERE {predicate}(l.geom, r.geom)
            """,
            [str(left_path), str(right_path)],
        ).fetchall()
        n = len(left_cols)
        return [
            {
                "left": dict(zip(left_cols, row[:n])),
                "right": dict(zip(right_cols, row[n:])),
            }
            for row in rows
        ]
    finally:
        if owns_con:
            con.close()
