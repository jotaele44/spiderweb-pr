# Aguadilla / Maleza Alta subsurface benchmark

Benchmark ID: `AGUADILLA_MALEZA_ALTA_SUBSURFACE_001`

Pinned anchor: `18.5091743, -67.1140566` (`EPSG:4326`).

## Purpose

This benchmark refines Spiderweb's subsurface, karst, cave/void and coastal-discharge workflow without permitting imagery or proximity to become identity proof. The benchmark is not a cave detector. It is an evidence-control and spatial-analysis fixture.

## Frozen input state

The benchmark configuration is `configs/subsurface_benchmarks/aguadilla_maleza_alta_001.json`. The five supplied visual fixtures are frozen there by byte size, pixel dimensions and SHA-256. Those hashes prove only byte identity of the supplied screenshots; they do not prove the vintage or byte identity of the underlying Apple/Google/Flightradar24 imagery.

## Four nested analysis windows

| Window | Radius | Purpose |
|---|---:|---|
| Z1 | 5,000 m | regional geology, karst, aquifer and hydrographic context |
| Z2 | 1,000 m | catchment, depressions, drainage convergence and terrain system |
| Z3 | 250 m | feature-scale depression, lineament, scarp and capture candidates |
| Z4 | 50 m | micro-scale surface morphology, possible entrances and shoreline/outlet screening |

`spiderweb.subsurface.benchmark.acquisition_bbox` creates conservative WGS84 discovery bboxes only. Certified metric distance/topology must be computed after acquisition in an appropriate projected/geodesic implementation; the discovery bbox cannot be promoted to certified geometry.

## Source denominator for this benchmark

The current repository already contains a broader subsurface source denominator. This benchmark additionally requires a site-specific frozen manifestation for each of the following families before a terminal result is possible:

1. exact geology at the anchor;
2. bare-earth LiDAR or highest-resolution authoritative terrain;
3. surface hydrography;
4. springs and wells;
5. caves and sinkholes;
6. historical imagery sufficient for persistence testing;
7. coastline;
8. integrated nearshore/offshore bathymetry.

Authoritative candidates include USGS I-569 (Aguadilla 1:20,000 geologic map), the Puerto Rico Planning Board geology/sinkhole/cave services, USGS Water Data monitoring locations, and NOAA NCEI Puerto Rico 1/9 arc-second CUDEM. The NOAA CUDEM source integrates topography and bathymetry and is referenced horizontally to NAD83 and vertically to PRVD02. Exact source responses/tiles must be retained and hashed before analysis.

Municipal planning material derived from USGS mapping reports Aymamón Limestone across most of Maleza Alta, with coastal beach deposits and local blanket-sand deposits also present. That is regional/site-context evidence only. The anchor's exact formation remains `OPEN_POINT_QUERY` until the point is bound to a source-native geology polygon; barrio membership or dominant formation is not sufficient identity proof.

## Evidence and promotion rules

All detected objects must remain in one of:

`OBSERVED | CANDIDATE | UNRESOLVED | VERIFIED`

A candidate cannot be promoted to `VERIFIED` as `CAVE`, `VOID`, `SUBSURFACE_CONDUIT`, `SUBMARINE_SPRING`, or `OCEAN_OUTLET` without independent identity evidence. Surface alignment, nearest-neighbour proximity, vegetation contrast, count equality and regional karst compatibility remain discovery/supporting evidence only.

### Competing explanations that must be retained

Land features must test at minimum: normal surface drainage, road/trail, parcel/land-use boundary, vegetation succession, illumination/shadow, natural scarp, closed depression and karst/collapse hypotheses.

Ocean/coastal features must test at minimum: breaking wave, reef/submerged rock, sand channel, sediment/turbidity plume, sun glint, imagery seam, bathymetric step and freshwater-discharge hypotheses.

Tied top evidence is `UNRESOLVED`; deterministic ranking does not break an evidentiary tie.

## Temporal persistence

For every Z2-Z4 candidate, historical imagery observations are to be classified independently as:

`PERSISTENT | SEASONAL | NEW | REMOVED | MOVED | SHADOW_DEPENDENT | VEGETATION_DEPENDENT | IMAGERY_ARTIFACT | UNRESOLVED`

Historical imagery is corroboration. It does not establish subsurface continuity unless another independent evidence class binds the connection.

## Required arithmetic and provenance gates

For each source family preserve: authority, service/page, layer/product, exact query/AOI, retrieval UTC, source update/vintage when available, raw bytes, SHA-256, schema, row/tile count, CRS, vertical datum where applicable, geometry type and any dimensional loss.

Every run must close `source = retained + excluded + unresolved`, preserve stable-ID uniqueness where IDs exist, reject silent nulls, reject unintended M:N multiplication, preserve full candidate sets and record contradictions instead of overwriting them.

## Current certification state

- anchor identity: `PASS`
- four-window benchmark contract: `PASS`
- visual-fixture byte freeze: `PASS`
- regional karst compatibility: `PASS` as contextual evidence
- exact point geology: `OPEN`
- source-native terrain: `OPEN`
- hydrography: `OPEN`
- springs/wells: `OPEN`
- cave/sinkhole AOI result: `OPEN`
- historical imagery persistence: `OPEN`
- coastline binding: `OPEN`
- bathymetry tile binding: `OPEN`
- four-zoom derived-candidate run: `BLOCKED` on source acquisition/runtime
- land-to-ocean connectivity identity: `UNRESOLVED`
- reusable skill training/promotion: `BLOCKED` until the benchmark is completed and verified

Therefore the benchmark is `PROVISIONAL`, not certified.

## Skill-training gate

Do **not** add a new active skillpack capability merely because this benchmark contract exists. Training/promotion is permitted only after source acquisition, four-window execution, temporal and falsification gates, candidate adjudication, arithmetic closure and zero unresolved residue inside the declared training claim. Passed control-plane artifacts should be reused; mutable source data should only be reacquired when intentionally creating a new versioned snapshot.
