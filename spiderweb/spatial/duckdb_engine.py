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

The spatial extension is never installed from this runtime. A certified
release must supply it in DuckDB's local extension directory or set
``SPIDERWEB_DUCKDB_SPATIAL_EXTENSION`` to a retained, checksum-bound file.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Optional

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MUNICIPIOS = REPO_ROOT / "data" / "municipios.geojson"
SPATIAL_EXTENSION_ENV = "SPIDERWEB_DUCKDB_SPATIAL_EXTENSION"

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


class SpatialExtensionUnavailable(RuntimeError):
    """Raised when the locally retained DuckDB spatial extension cannot load."""


class AmbiguousMunicipioError(ValueError):
    """Multiple containing source rows; no canonical identity is selected."""

    def __init__(self, candidates: list[dict]):
        self.candidates = tuple(candidates)
        super().__init__(
            f"Municipio lookup is unresolved: {len(candidates)} containing source rows"
        )


def _extension_locator(extension_path: Path | str | None) -> str:
    configured = (
        extension_path
        if extension_path is not None
        else os.environ.get(SPATIAL_EXTENSION_ENV)
    )
    if configured is None:
        return "spatial"
    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        raise SpatialExtensionUnavailable(
            f"DuckDB spatial extension does not exist: {path}. "
            f"Set {SPATIAL_EXTENSION_ENV} to a retained extension file."
        )
    return str(path)


def connect(*, extension_path: Path | str | None = None) -> "duckdb.DuckDBPyConnection":
    """Open an in-memory connection and load a local spatial extension.

    DuckDB's known-extension auto-install and auto-load features are disabled
    before loading. This function never executes ``INSTALL`` and therefore
    cannot silently turn an offline query into a runtime package download.
    """

    locator = _extension_locator(extension_path)
    con = duckdb.connect(":memory:")
    try:
        con.execute("SET autoinstall_known_extensions = false")
        con.execute("SET autoload_known_extensions = false")
        con.load_extension(locator)
    except Exception as exc:
        con.close()
        if isinstance(exc, SpatialExtensionUnavailable):
            raise
        raise SpatialExtensionUnavailable(
            "DuckDB spatial could not be loaded from local storage. "
            f"Pre-stage and checksum the extension, then set {SPATIAL_EXTENSION_ENV}; "
            "runtime installation is prohibited."
        ) from exc
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

    Returns the raw ``NAME`` of a unique containing source row, or ``""`` if
    no polygon contains the point or the file is missing. Boundary-only contact
    is excluded by ST_Contains. Overlapping/duplicate candidates raise
    AmbiguousMunicipioError with every whole source row retained. A spatial
    lookup supplies a source label, not independent canonical identity proof.
    """
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("Latitude and longitude must be finite")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude or longitude is outside its valid range")
    if not municipios_path.exists():
        return ""
    owns_con = con is None
    con = con or connect()
    try:
        result = con.execute(
            """
            SELECT *
            FROM ST_Read(?)
            WHERE ST_Contains(geom, ST_Point(?, ?))
            """,
            [str(municipios_path), lon, lat],
        )
        rows = result.fetchall()
        columns = [column[0] for column in result.description]
        if len(columns) != len(set(columns)):
            raise ValueError("Municipio source has duplicate output fields")
        candidates = [dict(zip(columns, row, strict=True)) for row in rows]
        if len(candidates) > 1:
            raise AmbiguousMunicipioError(candidates)
        if not candidates:
            return ""
        name = candidates[0].get("NAME")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "Containing municipio source row has no nonempty string NAME"
            )
        return name
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
