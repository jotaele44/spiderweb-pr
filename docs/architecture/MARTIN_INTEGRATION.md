# Martin integration architecture

## Decision

Spiderweb-PR uses Martin only as a replaceable geospatial delivery plane. Spiderweb remains authoritative for acquisition, frozen source bytes, provenance, schema/CRS validation, visibility, identity, analysis, CRIM querying, and certification.

## Current canary

The first canary is the public 2025 TIGER `municipios` layer because it already has:

- a reproducible Spiderweb ingestion path;
- a frozen provenance manifest;
- exact feature denominator 78;
- EPSG:4326 output;
- stable `GEOID` identifiers;
- an existing FastAPI `/geo/municipios.geojson` rollback path;
- an existing MapLibre polygon presentation path.

The source artifact recorded in `data/tiger/2025/manifest.json` has SHA-256 `adebd4e779e36ca4aecb69291af9e153e430a829cc4ca8a676f7d5f5197a5d76`.

## Authority graph

```text
Authoritative source
  -> Spiderweb ingestion
  -> frozen provenance manifest
  -> validated derived GeoJSON
  -> explicit delivery registry (non-authoritative)
  -> Martin
  -> TileJSON / MVT
  -> MapLibre
```

No arrow in the reverse direction establishes canonical identity. MVT geometry is clipped/quantized presentation geometry and must not replace the source geometry.

## Publication gates

1. A layer must exist in `configs/layer_catalog.yaml`.
2. Its visibility classification must permit the requested publication context.
3. It must be explicitly present in `configs/martin_delivery.yaml`.
4. It must be explicitly named in `martin/config.yaml`.
5. Its artifact hash/count/CRS must agree with the frozen provenance manifest.
6. `candidate` is not `published`.

Martin directory autodiscovery is forbidden for production configuration.

## Current storage boundary

The application database remains SQLite. PostGIS is not introduced merely to satisfy Martin. It is a later candidate only if dynamic vector scale, server-side spatial query, concurrency, or update frequency justify a separately certified migration.

## Rollback

The existing FastAPI `/geo/{layer}.geojson` path remains intact during the canary. Martin failure must not affect non-map FastAPI endpoints or mutate source artifacts.

## Next certification gates

- start a pinned Martin 1.13.0 runtime using `martin/config.yaml`;
- run `tests/test_martin_catalog_contract.py`;
- run `scripts/check_martin_canary.py`;
- wire `municipios` in MapLibre as a vector source through same-origin `/tiles`;
- compare source GEOID set with the union of served MVT feature identities;
- verify one known present and one known absent spatial control;
- test Martin unavailable/restart behavior;
- only then change `publication_state` beyond `candidate` or expand to additional layers.
