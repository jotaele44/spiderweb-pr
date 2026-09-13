# AOI Dry Run v1.1 — bounded implementation evidence

Date: 2026-09-12. PR: #357. Status: DRAFT / OPEN.

## Implemented boundary

The existing SpatialIntelligence mount calls the extended SpatialToolsPanel.
The previous measure/buffer/nearest implementation is preserved byte-for-byte
as SpatialToolsLegacy.tsx. The new panel mounts AoiMapWorkbench and the acquisition
plan panel, with mutually exclusive map interactions.

Draw / Finish / Undo / Clear and vertex editing are implemented. Polygon parts
and interior rings survive import and targeted edits. Imported GeoJSON is decoded
as strict UTF-8, preserving the original text (including a BOM when present) for
backend SHA-256 and lineage. Unsupported encodings are rejected, not replaced.
Interactive edits are capped at 1,000 handles without simplifying larger imported
AOIs. The backend accepts at most 20,000 vertices. The frontend import limit is
4 MiB; the total JSON request limit is 5 MiB.

The production API registers POST /spatial/aoi/plan. It accepts AOI geometry,
original import text, filters and a separate processing-buffer distance. It does
not accept a caller-provided bbox, catalog path, arbitrary URL, or source registry.
The backend derives the bbox and applies exact footprint intersection. All rows
in the examined snapshot remain in the plan, including exclusions and unresolved
geometries. Positive-area inclusion never comes from bbox contact alone.

The frontend consumes the same snake_case v1.1 wire schema as the backend. The
previous camelCase/snake_case mismatch is removed. Dry Run is available before a
first plan exists. Edits, filters, imports and clear invalidate earlier HTTP
responses. A returned plan must match the submitted AOI.

Plans expose full source footprints, original candidate records, canonical AOI,
processing geometry, both intersections, catalog hashes/counts, required-asset
arithmetic, known bytes and unknown-size counts. SHA-256 covers the full payload,
excluding only plan_id and plan_sha256, using sorted-key ASCII JSON. This is a
hash-bound export, not a signature, remote authenticity proof, or durable archive.

## Source adapter and readiness limits

The initial exact-footprint adapter accepts a configured GeoJSON FeatureCollection
snapshot with root-contained catalog_path, matching catalog_sha256 and explicit
catalog_record_count. Provider configuration owns provider_id/dataset/version;
feature properties own asset_id/source_url and product/date/resolution metadata.
The bounded denominator is that configured snapshot only. Source binding means
binding to the configured snapshot; upstream provider authenticity still requires
independent catalog provenance review.

The existing PRVI_1m_DEM_2018 configuration has no catalog path or URL binding and
uses VRT. It remains BLOCKED. No real public catalog has been acquired or bound by
this change. VRT and live TNM/NOAA discovery adapters remain OPEN. This work does
not replace the existing CLI downloader or certify it.

The planner performs no cache lookup or binary acquisition. cache_valid is zero;
cache_state is NOT_CHECKED. fetch_required is a conservative transfer-candidate
count pending cache inspection, not a measured cache miss count. Fetch remains
unconditionally disabled in the GUI and capabilities.fetch is false in the API.
No acquisition route is exposed. Usable-data coverage is null/UNKNOWN and overall
certification remains OPEN, even when bounded planning_gate is PASS.

A processing buffer uses planar UTM zone 20N metres, limited to the documented
Puerto Rico regional extent; the unbuffered AOI is never mutated. Zero buffer
requires no transformation. No geographic Cell_ID binding is inferred.

## Executed local verification

- 34 Python tests passed: exact relations, holes, concavity, multipart geometry,
  invalid topology/CRS/Z, nonfinite/boolean coordinates, strict JSON, row counts,
  catalog hashes, unbound/empty catalogs, identity collisions, duplicate residue,
  filters, processing buffer, raw lineage, path containment, HTTP API behavior,
  request size rejection, missing fetch route, schema and additive mount AST.
- 13 Node tests passed against the compiled production TypeScript parser and an
  actual Python-produced synthetic plan fixture. Tests reject row loss, empty
  READY, invalid counters, phantom cache claims, unresolved READY, touch-only
  inclusion, unsupported execution/coverage, and stale/mismatched AOI responses.
- Pure TypeScript contract compilation passed. TSX transpilation found no syntax
  diagnostics. Neither result establishes full application type-check/build PASS.

The dedicated AOI dry-run workflow installs server/geo/federation/dev extras and
runs all backend tests. The base suite explicitly skips this module when its
optional pyproj dependency is absent; that skip is not a verification PASS.

All source fixtures are synthetic and use TEST_ONLY / example.invalid identities.
They do not establish live-source acquisition, geographic coverage or GUI runtime
certification.

Reproduction (with project server/geo and test dependencies installed):

```sh
python -m pytest tests/test_aoi_planner.py -q
# From repository root; use the installed project TypeScript compiler:
./server/frontend/node_modules/.bin/tsc \
  server/frontend/src/modules/aoiContract.ts --strict --target ES2022 \
  --module commonjs --lib ES2022,DOM --outDir /tmp/aoi-contract-check
node tests/aoi_contract_runtime.cjs \
  /tmp/aoi-contract-check/aoiContract.js tests/fixtures/aoi_plan_v1_1.json
```

## Verification still OPEN

Full FastAPI application startup was not run locally (aiosqlite and
sse_starlette unavailable); the new router was exercised with FastAPI TestClient.
React/Vitest render tests were added but not executed because project npm
dependencies were unavailable and direct GitHub network resolution failed.
Full frontend typecheck/lint/build, MapLibre rendered interaction tests, and iPhone
portrait/landscape tests remain OPEN. No screenshot baseline is claimed.

The previous PR-head hosted CI frontend job 103585104913 reported failure; retrying
its log endpoint returned HTTP 404 / BlobNotFound. The root cause remains
UNRESOLVED, not attributed to these changes or to infrastructure without evidence.

## Remaining implementation denominator

Bind authoritative catalog snapshots and exact-footprint adapters; finish runtime
GUI/mobile verification; add existing-feature AOI via full authoritative geometry
(not viewport-clipped vector-tile fragments); add KML/KMZ/GPKG/Shapefile conversion;
add validated source-key cache, acquisition, hashing, format checks and valid-data
coverage. Add durable AOI/run storage, run history, resume and acquisition workers
before claiming POLYGON -> FILES certification. Preserve the full state-machine
contract in AOI_ACQUISITION_WORKBENCH_CONTRACT.md; v1.1 implements its dry-run subset.
