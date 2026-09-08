# Apple imagery external render provider

**Status:** PROVISIONAL  
**Provider:** `apple-mapkit`  
**Federation authority:** `spiderweb-pr`  
**Classification:** `EXTERNAL_RENDER_PROVIDER` / `NONCANONICAL`

## Scope

Apple Maps satellite and hybrid presentations may be exposed as interactive reference basemaps through documented Apple MapKit APIs. Apple Map Data is not a federation source manifestation and must not be harvested, persisted, mosaicked, republished, or used as the sole basis for entity identity.

Canonical geometry, attributes, source provenance, and investigation evidence remain independent of the render provider. Switching providers must change presentation only.

## Architecture

```text
canonical federation geometry
        |
        +--> MapLibre runtime (current canonical browser renderer)
        |
        +--> external render provider boundary
                |
                +--> Apple MapKit (standard / satellite / hybrid)
```

`SpatialRuntime` is currently MapLibre-shaped at scene configuration and the live Spiderweb overlay path still uses `MapLibreRuntime.getMapLibreInstance()`. Therefore provider declaration and observation provenance can land now, but Apple cannot be declared overlay-parity complete until overlays are moved behind a renderer-neutral adapter.

## Required gates

| Gate | Required state before live enablement |
|---|---|
| Provider policy contract | PASS |
| No pixel persistence | PASS |
| No tile harvesting/prefetch archive | PASS |
| No derived Apple map database | PASS |
| Attribution preserved | PASS |
| Credential-free mock tests | PASS |
| Generic layer adapter | PASS |
| Canonical overlay parity | PASS |
| Camera round-trip | PASS |
| Provider failure fallback | PASS |
| Observation provenance | PASS |
| Tracking-use policy gate | PASS where applicable |
| Apple credentials | provision LAST |

## Observation provenance

A durable observation stores only federation-owned metadata:

- local observation identifier;
- provider identifier (`apple-mapkit`);
- observation UTC;
- center coordinates and zoom/camera state;
- selected map type;
- optional local target entity identifier;
- investigator-authored note;
- evidence class `VISUAL_CORROBORATION`;
- identity effect `NONE`.

Provider pixels are not stored in the observation record.

## Historical imagery

Apple imagery is not the federation historical-imagery authority. Dated orthophotos, aerials, or other historical raster sources require an independently permitted source manifestation, acquisition date, provenance record, and retention rights.

## Current residue

- `OPEN`: renderer-neutral layer/overlay adapter.
- `OPEN`: Apple MapKit runtime implementation and mock runtime tests.
- `OPEN`: camera and overlay parity regression suite.
- `OPEN`: provider-unavailable fallback UI.
- `OPEN`: downstream repository adapters.
- `BLOCKED_BY_POLICY_GATE`: Skywatcher tracking presentation until the intended Apple MapKit usage is proven compatible with the applicable Apple Maps terms/platform context.
- `DEFERRED`: Apple Maps identifiers, keys, tokens, and live authorization.

No `APPLE_MAPKIT_EXTERNAL_RENDER_PROVIDER CERTIFIED` claim is permitted while any item above remains open or blocked.
