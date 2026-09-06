# DuckDB spatial engine

`spiderweb/spatial/duckdb_engine.py` provides an embedded spatial-SQL
alternative to writing a new GeoPandas/Shapely script for every ad hoc
geospatial question.

## When to use it

- **Ad hoc spatial joins or predicate queries** across GeoJSON artifacts
  already on disk (`data/municipios.geojson`, TIGER layers, gazetteer output,
  and similar sources).
- **One-off exploratory queries** that benefit from SQL predicates and joins.

## When not to use it

- `scripts/geocode_pr.py`'s `municipio_from_point` stays the hot path for
  harvester reverse-geocoding. It is standard-library-only by design.
- Existing GeoPandas/Shapely workflows do not need to be rewritten merely
  because the DuckDB adapter exists.

## Why DuckDB, not a hosted spatial service

The repository's active datasets are Puerto-Rico-scoped and fit local
single-machine processing. DuckDB spatial supplies useful `ST_*` operations
without a cluster, hosted database, account, or metered service. The mature
local GIS stack remains preserved.

## Python dependency

```bash
pip install -r requirements-spatial.txt
# or:
pip install -c constraints.txt -e ".[spatial]"
```

Installing the Python package does not authorize a later runtime extension
download.

## Spatial extension acquisition boundary

`duckdb_engine.connect()` now disables DuckDB's known-extension auto-install
and auto-load settings before loading spatial. It never executes `INSTALL`.

A release or analysis environment must provide spatial through one of these
local paths:

1. DuckDB's already populated local extension directory; or
2. a retained extension file named by
   `SPIDERWEB_DUCKDB_SPATIAL_EXTENSION`.

```bash
export SPIDERWEB_DUCKDB_SPATIAL_EXTENSION=/opt/spiderweb/extensions/spatial.duckdb_extension
```

The extension file must eventually appear in the offline dependency manifest
with, at minimum:

- DuckDB version and platform/architecture binding;
- original acquisition source;
- retrieval UTC;
- byte size;
- SHA-256;
- license and redistribution status;
- the release profiles that consume it.

If no local extension is available, the adapter raises
`SpatialExtensionUnavailable`. It does not attempt the network and does not
silently fall back to incomplete geometry behavior.

The current PR closes the **runtime download** defect only. It does not certify
`SELF_CONTAINED_RELEASE` or `OFFLINE_REPRODUCIBLE_BUILD` until the actual
extension bytes and manifest are frozen and the disconnected tests run.

## API

```python
from spiderweb.spatial.duckdb_engine import municipio_from_point, spatial_join

municipio_from_point(18.42, -66.07)  # -> "San Juan"

spatial_join(
    "data/municipios.geojson",
    "data/some_layer.geojson",
    predicate="ST_Intersects",
)
```

`predicate` is checked against an explicit allowlist of DuckDB spatial binary
predicate functions, preventing arbitrary SQL injection through that argument.

`tests/test_duckdb_spatial.py` always verifies the no-install behavior with a
controlled connection. Geometry parity tests execute when locally retained
spatial-extension bytes are available and otherwise skip with an explicit
reason rather than reaching the network.
