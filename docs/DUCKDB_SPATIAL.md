# DuckDB spatial engine

`spiderweb/spatial/duckdb_engine.py` provides an embedded spatial-SQL
alternative to writing a new GeoPandas/Shapely script for every ad hoc
geospatial question.

## When to use it

- **Ad hoc spatial joins or predicate queries** across GeoJSON artifacts
  already on disk (`data/municipios.geojson`, TIGER layers, gazetteer
  output, ...) — a `spatial_join()` call and a predicate name, instead of
  loading both files into GeoPandas and writing a join by hand.
- **One-off exploratory queries** an analyst wants to run interactively.

## When *not* to use it

- `scripts/geocode_pr.py`'s `municipio_from_point` stays the hot path for
  harvester reverse-geocoding — it's stdlib-only by design, with no runtime
  dependency to install. `duckdb_engine.municipio_from_point` is an
  additive, SQL-based alternative for new call sites that specifically want
  it, not a replacement.
- Anything already expressed cleanly with GeoPandas/Shapely (the `geo`
  extra) doesn't need to be rewritten in SQL just because this module
  exists.

## Why DuckDB, not Spark/Sedona/Wherobots

Every dataset this repo processes is Puerto-Rico-scoped and megabytes in
size (see `RECOMMENDATIONS.md`) — there's no documented scaling bottleneck
anywhere in this codebase. DuckDB's `spatial` extension gives real spatial
SQL (joins, predicates, `ST_*` functions) without a cluster, an external
service, or a new operational surface — the right amount of tooling for
this repo's actual scale. Reach for something heavier only if a producer
starts ingesting data that no longer fits single-machine memory.

## Install

```bash
pip install -r requirements-spatial.txt
# or:
pip install -c constraints.txt -e ".[spatial]"
```

The `spatial` DuckDB extension itself is installed/loaded at runtime
(`INSTALL spatial; LOAD spatial;`, handled by `duckdb_engine.connect()`) —
not a separate pip package.

## API

```python
from spiderweb.spatial.duckdb_engine import municipio_from_point, spatial_join

# Point-in-polygon reverse geocode (same contract as scripts/geocode_pr.py).
municipio_from_point(18.42, -66.07)  # -> "San Juan"

# Spatial join between any two GeoJSON files.
spatial_join(
    "data/municipios.geojson",
    "data/some_layer.geojson",
    predicate="ST_Intersects",  # or ST_Contains / ST_Within / ST_Touches / ST_Crosses / ST_Overlaps
)
```

`predicate` is checked against an explicit allow-list of DuckDB spatial's
binary predicate functions, so it can't be used to inject arbitrary SQL.

See `tests/test_duckdb_spatial.py` for more examples, including parity
checks against `scripts/geocode_pr.py`'s hand-rolled point-in-polygon.
