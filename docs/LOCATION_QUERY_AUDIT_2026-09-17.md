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

The canonical v1 LOCATION_QUERY registry freezes 15 provider families/lanes with explicit readiness rather than flattening capability asymmetry:

| Provider | Family | State |
|---|---|---|
| USGS_3DEP_1M | elevation | READY |
| PRVI_1m_DEM_2018 | elevation | PROVIDER_BINDING_OPEN |
| NCEI_COASTAL_DEM | coastal_elevation | READY |
| NASA_GIBS_IMAGERY | satellite_imagery | READY |
| SENTINEL_HUB_IMAGERY | satellite_imagery | READY_WITH_CREDENTIALS |
| COPERNICUS_CDSE_IMAGERY | satellite_imagery | READY_WITH_CREDENTIALS |
| PRPB_GEOLOGY_KARST | geology_karst | READY_SPECIALIZED |
| PR_AQUIFERS_WELLS_SPRINGS | hydrogeology | READY_SPECIALIZED |
| PR_MARINE_LIDAR_TOPOBATHY | marine_topobathy | READY_SPECIALIZED |
| SSURGO_SOILS | soils | RESOLVER_ONLY |
| USGS_3DHP_NHD | hydrography | RESOLVER_ONLY |
| USFWS_NWI | wetlands | READY_SPECIALIZED |
| FEMA_NFHL | flood_hazard | RESOLVER_ONLY |
| USACE_GENERAL_GIS | federal_infrastructure | RESOLVER_ONLY |
| USACE_PORTS_NAV | ports_navigation | READY_SPECIALIZED |

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


## 2026-09-17 hardening update

- Provider denominator is now 15 after separating the bounded USACE ports/navigation subset from the still-open general USACE enterprise denominator.
- SSURGO now emits bounded SurveyAreaPoly + MapunitPoly WFS request specifications but remains `RESOLVER_ONLY`; the in-repo MUKEY→COKEY→child production chain is still open.
- 3DHP now freezes FeatureServer metadata first and remains `RESOLVER_ONLY` pending a release-layer denominator.
- NWI has a bounded Wetlands FeatureServer layer and is `READY_SPECIALIZED`.
- FEMA NFHL remains `RESOLVER_ONLY`; WMS capability binding is not vector-feature identity.
- Geology/karst and hydrogeology reuse the existing verified queryable subsurface source denominator and are `READY_SPECIALIZED` without promoting reference-only sources.
- Place-name geocoding remains discovery-only and now freezes raw provider bytes before interpreting candidates.
- GitHub Actions remains `BLOCKED_ACTIONS_INFRASTRUCTURE` where jobs terminate with zero executed steps; that is not code-test evidence.


## 2026-09-17 denominator-closure update

The provider denominator is now 16 after adding the bounded FEMA Puerto Rico ABFE lane separately from FEMA NFHL. Source taxonomy remains separate from canonical identity.

New implementation artifacts:
- `spiderweb/provider_denominators.py`: freezes ArcGIS layer, ArcGIS service-root, and WMS named-layer denominators from preserved raw bytes + matching acquisition receipt SHA-256.
- `scripts/freeze_location_provider_denominator.py`: operator CLI for those denominator freezes.
- `spiderweb/denominator_chain.py`: emits dependent metadata/query plans from a frozen parent denominator.
- `scripts/build_location_denominator_stage.py`: CLI for USACE service-root -> per-service metadata and ArcGIS layer denominator -> AOI feature queries.
- `spiderweb/ssurgo_chain.py`: MapunitPoly raw bytes -> exact numeric MUKEY denominator -> mapunit/component SDA POST plan.
- `scripts/location_query_fetch.py` v1.1: bounded GET + explicit JSON POST with request-body SHA-256 and raw response preservation.
- `spiderweb/place_resolver.py`: discovery-only geocoder preserving the full candidate set; explicit analyst candidate binding is required before LOCATION_QUERY geometry exists.

Certification corrections:
- USGS 3DHP/NHD is `RESOLVER_ONLY` again. Six observed layer candidates remain preserved as provisional registry context, but no frozen raw FeatureServer metadata receipt on this branch yet proves the release denominator. Production routing therefore emits only `feature_service_metadata` until that denominator is frozen.
- NWI remains `READY_SPECIALIZED` because the exact Wetlands FeatureServer layer is explicitly bound; feature identity remains source-manifestation identity.
- FEMA NFHL remains `RESOLVER_ONLY`; WMS named-layer inventory is metadata, not vector-feature identity.
- FEMA PR ABFE remains `RESOLVER_ONLY` until its MapServer layer denominator is frozen and AOI layer-query behavior is executed.
- USACE general GIS now emits an explicit service-root metadata request and can freeze the returned service denominator; the ports/navigation subset remains separately `READY_SPECIALIZED`.

No provider may be promoted merely because a parser or planner exists. Runtime acquisition, denominator arithmetic, stable-ID/cardinality checks, and provenance hashes remain downstream certification gates.
