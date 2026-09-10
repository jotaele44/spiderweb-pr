# Apple imagery external-render provider

Status: **PROVISIONAL / NOT CERTIFIED**

Apple MapKit JS is integrated on this branch as a noncanonical external renderer candidate. Apple Map Data is not a federation-owned source dataset and Apple provider pixels are not persisted, harvested, prefetched into offline archives, or promoted into a secondary map database.

## Implemented credential-free foundation

- `governance/external_render_provider_v1.json` — provider authority/retention boundary.
- `governance/imagery_provider_registry_v1.json` — federation render/source manifestation registry and fallback states.
- `governance/imagery_source_bindings_v1.json` — exact retained imagery source bindings kept separate from render providers.
- `ExternalRenderProvider.ts` — typed render capability and observation provenance model.
- `SpatialAdapters.ts` — renderer-neutral layer, marker, camera, capability and unsupported-state contracts.
- `MapLibreSpatialAdapters.ts` — MapLibre implementation preserving existing source/layer/marker/camera behavior.
- `LimitedSpatialAdapters.ts` — explicit camera-only capability surface for the current Cesium domain implementation.
- `AppleSpatialAdapters.ts` — Apple capabilities derived from the supplied/tested bridge; unsupported capabilities fail closed.
- `AppleMapKitRuntime.ts` — provider-native MapKit lifecycle using center + camera distance.
- `MapKitJsLiveBridge.ts` — documented MapKit JS initialization/map-type/polygon/custom-marker bridge with injected authorization callback and no embedded credentials.
- `SpatialIntelligence.tsx` — migrated off raw `maplibre-gl`; semantic adapters only.
- renderer/provider regression tests and `RENDERER_NEUTRAL_PARITY_MATRIX.md`.

## Current Apple semantic capability state

Implemented in credential-free bridge code:

- standard / satellite / hybrid map type selection;
- provider-native WGS84 center;
- provider-native camera distance in meters;
- GeoJSON Polygon/MultiPolygon → MapKit `PolygonOverlay` semantic path;
- investigation marker → custom MapKit annotation semantic path;
- semantic overlay/annotation cleanup.

Explicitly unsupported/unverified:

- canonical MapLibre zoom ↔ Apple camera-distance equivalence;
- high-volume GeoJSON point-circle parity;
- Martin vector-tile delivery inside Apple (domain falls back to canonical GeoJSON where supported);
- live Apple authorization/runtime smoke;
- live basemap failure mapping/fallback;
- live attribution layout regression.

## Canonical-data invariant

Provider switching changes presentation only. It must not mutate canonical geometry, stable IDs, source bytes/hashes, entity identity, source/evidence classification, investigation provenance, or retained imagery assets.

Any human observation made while viewing Apple imagery is an `OBSERVATION` / `VISUAL_CORROBORATION` record with `identityEffect = NONE` unless independently supported by authoritative identity evidence.

## Credential policy

No Apple Maps token, private key, Team ID secret material, or other production credential belongs in this branch. `MapKitJsLiveBridge.ts` accepts an injected authorization callback so the real token provider can be provisioned only after credential-free code/tests/invariants otherwise pass.

## Current blockers

1. GitHub Actions jobs are failing before executable steps/logs are provided, so authored tests are not execution PASS.
2. Apple canonical camera conversion requires measured viewport/latitude/device-pixel-ratio evidence; no guessed transform is permitted.
3. Live MapKit JS behavior and attribution cannot be certified without the deferred authorization stage.
4. High-volume point-circle equivalence is unresolved and advertises unsupported.
5. Cesium overlay parity is outside its currently implemented camera-only domain adapter.
6. Cross-repo Apple runtime smoke remains OPEN.
7. Skywatcher tracking-use policy remains separately gated.
8. Final branch freeze must incorporate the current `main` head before certification.

See `docs/RENDERER_NEUTRAL_PARITY_MATRIX.md` for capability set algebra and exact certification residue.

## Certification rule

Neither `RENDERER_NEUTRAL_SPATIAL_RUNTIME_PASS` nor `APPLE_MAPKIT_EXTERNAL_RENDER_PROVIDER CERTIFIED` may be issued until their declared scope has zero material unresolved residue and every required test has actually executed against frozen inputs/runtime revisions.
