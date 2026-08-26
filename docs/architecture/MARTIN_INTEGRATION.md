# Martin integration architecture

## Decision

Spiderweb-PR uses Martin only as a replaceable geospatial delivery plane. Spiderweb remains authoritative for acquisition, frozen source bytes, provenance, schema/CRS validation, visibility, identity, analysis, CRIM querying, and certification.

## Validated canary

The first validated canary is the public 2025 TIGER `municipios` layer because it has:

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
6. `validated` is not `published`.

Martin directory autodiscovery is forbidden for production configuration.

## Runtime pin

The canary is pinned to MapLibre Martin `1.13.0` using the official Linux musl release asset recorded in `martin/runtime.lock.json`:

- asset: `martin-x86_64-unknown-linux-musl.tar.gz`
- SHA-256: `96d6415ca3b18f843eb0ef28f44d34b96c494b192e9ef7e7289b3bc88612009d`

The CI runtime refuses to execute the canary unless that asset digest matches.

## P5 certification receipts

GitHub Actions workflow `Martin municipios canary`, run `31864754904`, certified the pre-promotion canary at commit `6aa0ef2762a4d09dc9e7bd907192b5f3accfcc16`.

Runtime certification passed all of the following:

- immutable Martin 1.13.0 asset digest and version verification;
- deterministic regeneration of the TIGER municipios GeoJSON;
- exact 78-feature denominator and frozen GeoJSON SHA-256;
- Martin health and an exact catalog source set of `{municipios}`;
- TileJSON availability;
- decoded MVT logical identity reconstruction;
- source GEOID set equals MVT GEOID set, count 78, symmetric difference 0;
- MVT content-type control;
- non-empty known tile control;
- ETag presence and `If-None-Match` -> HTTP 304;
- outside-Puerto-Rico tile feature-leakage control;
- unsupported/invalid zoom feature-leakage control;
- Martin-down detection while Spiderweb FastAPI remains independently reachable over HTTP;
- clean Martin restart and catalog recovery;
- missing authorized source fails closed;
- corrupt authorized source fails closed.

Frontend A/B certification in the same workflow run passed:

- lint;
- TypeScript typecheck;
- build with `VITE_MUNICIPIOS_DELIVERY=martin`;
- build with `VITE_MUNICIPIOS_DELIVERY=geojson`.

The GeoJSON switch is the deterministic rollback control. `tracts`, `places`, and `barrios` remain on the existing GeoJSON delivery path in this phase.

## Current storage boundary

The application database remains SQLite. PostGIS is not introduced merely to satisfy Martin. It is a later candidate only if dynamic vector scale, server-side spatial query, concurrency, or update frequency justify a separately certified migration.

## Rollback

The existing FastAPI `/geo/{layer}.geojson` path remains intact. `VITE_MUNICIPIOS_DELIVERY=geojson` switches the municipios presentation back to the established FastAPI GeoJSON path without changing canonical data or Martin configuration. Martin failure does not alter source artifacts or the application database.

## Promotion boundary

`municipios` is now `published` in the non-authoritative Martin delivery registry, reached via an explicit operator-authorized `validated` -> `published` transition (see `martin/README.md`'s "Promotion gate" section for the full history and rollback path). Expansion to `tracts|places|barrios`, and the `wetlands_nwi_prvi` scale benchmark, remain separate gates — publishing `municipios` does not admit any other source.
