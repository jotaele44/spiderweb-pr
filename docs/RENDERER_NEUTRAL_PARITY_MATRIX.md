# Renderer-Neutral GIS Parity Matrix

Status: **PROVISIONAL / NOT CERTIFIED**

Scope: `SpatialIntelligence` presentation semantics on `feat/apple-imagery-provider`.
This document does not claim pixel equivalence, provider-data identity, or live Apple authorization.

## Capability matrix

| Capability | MapLibre | Apple MapKit JS bridge | Cesium regional runtime | Certification state |
|---|---:|---:|---:|---|
| canonical GeoJSON polygon overlay | YES | CANDIDATE_IMPLEMENTED | NO | OPEN until executed tests + live Apple smoke |
| canonical GeoJSON point-circle layer | YES | NO | NO | MAPLIBRE_ONLY |
| Martin vector-tile polygon | YES | NO; canonical GeoJSON fallback | NO | MAPLIBRE_ONLY delivery optimization |
| investigation marker | YES | CANDIDATE_IMPLEMENTED | NO | OPEN until executed tests + live Apple smoke |
| canonical zoom camera | YES | NO | YES | APPLE OPEN |
| provider-native camera distance | N/A | YES | N/A | APPLE_ONLY, not canonical zoom |
| resize lifecycle | YES | provider-managed/live observation required | YES | APPLE OPEN |
| popup API used by SpatialIntelligence | NOT USED | NOT USED | NOT USED | OUTSIDE CURRENT DOMAIN SCOPE |
| feature-selection API used by SpatialIntelligence | NOT USED | NOT USED | NOT USED | OUTSIDE CURRENT DOMAIN SCOPE |
| basemap error signal | YES | OPEN | runtime-specific | OPEN |
| attribution preservation | OSM runtime | APPLE NATIVE REQUIRED | runtime-specific | APPLE LIVE GATE |
| standard basemap | provider style | YES | N/A | APPLE CANDIDATE |
| satellite basemap | external provider dependent | YES | imagery layer dependent | APPLE CANDIDATE |
| hybrid basemap | external provider dependent | YES | imagery layer dependent | APPLE CANDIDATE |

`YES` means implemented in code for that renderer. It does **not** mean certified unless the relevant execution gate has passed.

## Set algebra — MapLibre A vs Apple B

### INTERSECTION

Implemented/candidate semantic intersection:

- WGS84 center representation;
- canonical GeoJSON polygon presentation;
- investigation markers with accessible labels and activation;
- lifecycle removal/cleanup;
- standard visual map presentation.

The intersection is **not certified** because Apple execution still lacks credentials/live runtime and GitHub CI is not obtaining runners.

### A_ONLY

- canonical MapLibre zoom semantics;
- Martin vector-tile polygon delivery;
- native high-volume GeoJSON circle layer;
- current source-scoped MapLibre tile/error event behavior;
- current MapLibre raster-style configuration.

### B_ONLY

- Apple provider-native `cameraDistance` in meters;
- Apple `standard`, `satellite`, and `hybrid` map types;
- Apple-native imagery/labels/attribution behavior.

### UNION

All capabilities in INTERSECTION + A_ONLY + B_ONLY.

### SYMMETRIC_DIFFERENCE

`A_ONLY ∪ B_ONLY`. None of these capabilities may be silently coerced into equivalence. The adapter advertises unsupported states explicitly and the domain falls back from Martin vector delivery to the same canonical GeoJSON where applicable.

## Set algebra — MapLibre A vs Cesium C

### INTERSECTION

- runtime/container lifecycle;
- canonical center/zoom camera contract presently implemented by `SpatialRuntime`;
- resize.

### A_ONLY

- SpatialIntelligence GeoJSON polygons/circles;
- Martin vector polygons;
- investigation markers;
- MapLibre basemap source error semantics.

### C_ONLY

- regional 3D globe/terrain presentation semantics.

### SYMMETRIC_DIFFERENCE

All current overlay and 3D-specific behavior. Cesium therefore advertises camera-only semantic adapters rather than silently receiving a null raw-map handle.

## Direct-renderer leakage gate

`SpatialIntelligence.tsx` must not contain:

- `maplibre-gl` import;
- `maplibregl.*` calls;
- direct `.addSource(` or `.addLayer(` calls;
- `getMapLibreInstance`;
- `mapRef` transitional escape hatch.

These constraints are regression-tested in `SpatialIntelligence.renderer-neutral.test.ts`.

## Presentation-only provider-switch invariant

Changing renderer/provider may change only presentation state. It must not mutate:

- canonical GeoJSON input;
- source bytes or source hashes;
- stable IDs;
- entity identity;
- source/evidence classification;
- investigation observation provenance;
- retained imagery assets.

Apple provider pixels are never a retained source manifestation.

## OPEN / BLOCKED residue

1. **BLOCKED — GitHub Actions execution:** current PR jobs fail before steps execute / runner logs are produced; authored tests are therefore not execution PASS.
2. **OPEN — Apple camera conversion:** no measured canonical zoom ↔ `cameraDistance` transform exists across latitude/viewport/device-pixel-ratio conditions.
3. **OPEN — Apple live runtime:** authorization/token is deliberately deferred; live factory/overlay behavior is not smoke-tested against the real SDK.
4. **OPEN — Apple high-volume point layer:** no performance-equivalent native circle implementation is certified; capability remains false.
5. **OPEN — Apple basemap failure/fallback event mapping:** runtime-specific failure observation is not yet bound to the generic basemap error state.
6. **OPEN — Apple attribution live regression:** must verify provider-native attribution remains visible under actual layouts/device widths.
7. **OPEN — Cesium overlays:** existing regional runtime remains camera-only for this domain; no false parity claim.
8. **OPEN — branch ancestry:** feature branch is one documentation-only main commit behind at the recorded checkpoint; no GIS conflict observed, but exact final merge head must include current main before freeze.
9. **OPEN — downstream cross-repo runtime smoke:** AguaYLuz, MoneySweep, Skywatcher, OVNIS and TheHub bindings are not live-tested against an Apple renderer.
10. **OPEN — Skywatcher policy gate:** commercial tracking/asset-tracking use remains excluded pending exact use-case/legal adjudication.

## Certification rule

`RENDERER_NEUTRAL_SPATIAL_RUNTIME_PASS` may be issued only when material residue within the declared parity scope is zero and every required test has actually executed. Script authorship, mergeability, deterministic adapter behavior, or a credential-free fake runtime are not substitutes for certification evidence.
