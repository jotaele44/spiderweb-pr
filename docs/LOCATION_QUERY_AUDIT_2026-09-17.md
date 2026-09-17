# LOCATION_QUERY capability audit — 2026-09-17

Base snapshot: `85089a888391eb494ad6b047831684cd6b301162` (`main` at audit start).

This audit is bounded to current `spiderweb-pr` repository manifestations. Search absence is not source absence.

## Existing capability

- `tools/spatial_aoi_fetcher.py`: AOI -> authoritative source-tile catalog -> cache validation -> missing-byte fetch -> task-local VRT. Cell_ID geographic binding remains blocked pending a certified grid transform.
- `tools/source_manifestation_seed.py`: USGS TNM bbox discovery, authoritative download URL capture, and provider-header footprint binding for 1 m DEM manifestations.
- `source_adapters/ncei_coastal_dem`: AOI-aware coastal DEM discovery/fetch lane.
- `imagery/providers`: NASA GIBS, Sentinel Hub, and Copernicus provider implementations.
- `spiderweb/subsurface/sources.py`: verified/queryable geology, karst, cave, aquifer, well, spring and selected USACE source manifestations.
- `pipeline/pr_marine_datasets.py`: specialized marine/topobathy source lane.

## Unified provider denominator

The canonical v1 LOCATION_QUERY registry freezes 14 provider families/lanes with explicit readiness rather than flattening capability asymmetry:

| Provider | Family | State |
|---|---|---|
| USGS_3DEP_1M | elevation | READY |
| PRVI_1m_DEM_2018 | elevation | PROVIDER_BINDING_OPEN |
| NCEI_COASTAL_DEM | coastal_elevation | READY |
| NASA_GIBS_IMAGERY | satellite_imagery | READY |
| SENTINEL_HUB_IMAGERY | satellite_imagery | READY_WITH_CREDENTIALS |
| COPERNICUS_CDSE_IMAGERY | satellite_imagery | READY_WITH_CREDENTIALS |
| PRPB_GEOLOGY_KARST | geology_karst | RESOLVER_ONLY |
| PR_AQUIFERS_WELLS_SPRINGS | hydrogeology | RESOLVER_ONLY |
| PR_MARINE_LIDAR_TOPOBATHY | marine_topobathy | READY_SPECIALIZED |
| SSURGO_SOILS | soils | NOT_IMPLEMENTED |
| USGS_3DHP_NHD | hydrography | NOT_IMPLEMENTED |
| USFWS_NWI | wetlands | NOT_IMPLEMENTED |
| FEMA_NFHL | flood_hazard | NOT_IMPLEMENTED |
| USACE_GENERAL_GIS | federal_infrastructure | RESOLVER_ONLY |

## Certification boundaries

`READY` means a repository implementation path exists; it does not prove live provider availability at every future execution.

`RESOLVER_ONLY` means source discovery/query knowledge exists but the family has not yet been normalized behind the generic byte-acquisition contract.

`NOT_IMPLEMENTED` preserves the family in the routing denominator without pretending its adapter exists.

`PROVIDER_BINDING_OPEN` means acquisition machinery exists but an authoritative catalog/URL binding is incomplete.

## Non-promotion rules

- NO_COVERAGE != SOURCE_ABSENCE.
- MISSING_PROVIDER_BINDING != MISSING_DATASET.
- Family identity != source-manifestation identity.
- Geocoding/search is discovery until converted to bounded spatial geometry.
- Plan before download.
- Preserve authoritative bytes before derivation.
- Geographic Cell_ID binding remains blocked until transform certification passes.

## Actions implemented in PR #366

- canonical LOCATION_QUERY JSON schema;
- unified provider/readiness registry;
- planning router and CLI;
- reference Puerto Rico AOI corpus;
- offline provider-registry audit;
- routing and registry regression tests;
- explicit documentation of incomplete provider families.

## Open implementation denominator

1. integrate certified SSURGO AOI workflow as a repository adapter;
2. implement USGS 3DHP/NHD provider;
3. implement USFWS NWI provider;
4. implement FEMA NFHL provider;
5. unify the general USACE services catalog;
6. add discovery-only place-name geocoding -> bounded AOI;
7. execute/freeze the three reference AOIs when CI/runner infrastructure is available.

## CI status

The initial PR workflow runs failed before executing steps (`steps=[]`) across CI and federation gates. Those runs are classified `BLOCKED_ACTIONS_INFRASTRUCTURE`, not source-code test failures. Script success and file creation are not treated as certification.
