# D01, D11, D12 — Existing capability and reuse matrices

Read at spiderweb-pr `00ce0f9e8fec2a5c764881bf71ec00915583eb60`,
thehub-pr `36a08974dda53c971c2283f019318e17a14d43df` and
mucaro-ai `13ad436668dbc26712ec53b163e64dcf972e16d0`. All rows are `FACT` from
reading the files named, unless marked otherwise. Nothing in this audit was
established by running the code, except where a test is named.

**Finding.** Most of what the directive proposes exists, but in separate lanes
that each keep their own registry and receipt format. Six backend
responsibilities and ten frontend modules do not exist at all. The work is
mainly joining, not building.

## D12 — Backend modules

| ID | Responsibility | State | Reuse | Missing |
|---|---|---|---|---|
| B01 | Source registry | PARTIAL | Seven separate registries; see D02 | One index over them. Do not merge them. |
| B02 | Dataset registry | PARTIAL | `data_sources/elevation/dem_platform_catalog.yml`, `source_adapters/dem_platform/catalog.py` (elevation only) | Other dataset families |
| B03 | Dataset version registry | ABSENT | Version exists only as a field (`Dataset_Version` in `registry/spatial/source_manifestations.json`) | The registry |
| B04 | Native asset ledger | PARTIAL | `registry/spatial/source_manifestations.json`, `tools/source_manifestation_seed.py`; extended for the pilot in `registry/geo_sar/pilot_001_asset_ledger.json` | Checksums, verified metadata, families other than 3DEP |
| B05 | Segment registry | PARTIAL | Grid V2: `spiderweb/geographic_grid_v2.py` | A review record per segment |
| B06 | Geographic context resolver | PARTIAL | `spiderweb/gis_location.py`, `spiderweb/place_resolver.py` | Barrio and watershed resolution |
| B07 | Spatial intersection | EXISTS | `spiderweb/grid_v2_geometry_bindings.py` (`bind_exact_polygon`, `bind_exact_line`) | — |
| B08 | Dataset applicability | PARTIAL | `spiderweb/location_query.py`, `tools/spatial_aoi_fetcher.py` | Applicability by family and period |
| B09 | Source catalogue discovery | PARTIAL | `spiderweb/access_points/discovery.py`, `spiderweb/access_points/acquisition.py`, `spiderweb/provider_denominators.py` | A shared entry point |
| B10 | Acquisition planner | PARTIAL | `tools/spatial_aoi_fetcher.py`, `spiderweb/denominator_chain.py` | Priority by segments unlocked |
| B11 | Resumable retrieval | PARTIAL | `tools/spatial_aoi_fetcher.py` (`_download_resumable`) | Checkpointed, ledger-driven retrieval |
| B12 | Integrity verification | EXISTS, fragmented | `spiderweb/access_points/products.py` (`DownloadSession`), `tools/gis_evidence/core.py` | One call site |
| B13 | Original evidence storage | PARTIAL | `scripts/source_adapters/pr_hydrography/core.py` (`ImmutableSnapshotStore`), `pipeline/marine_sources.py` (`freeze_http_response`) | Content-addressed store for large rasters |
| B14 | Metadata normalisation | PARTIAL | `imagery/manifest.py`, per-adapter code | Shared record shape (D03) |
| B15 | Evidence rendering | PARTIAL | `server/backend/eri_imagery.py`, `martin/`, `viz_engine/` | Rendering of acquired rasters by asset |
| B16 | Comparison eligibility | PARTIAL | `spiderweb/site_timeline/epoch.py`, `spiderweb/site_timeline/timeline.py` | Datum, licence, independence checks |
| B17 | Comparison method registry | ABSENT before this work | Now `registry/geo_sar/comparison_methods.json` (CANDIDATE, nothing qualified) | Qualification |
| B18 | Comparison execution | PARTIAL | `scripts/run_dem_vs_3dep_lidar.py`, `imagery/compare.py`, `tools/gis_evidence/core.py` | Execution bound to segments |
| B19 | Observation registry | PARTIAL | `spiderweb/remote_monitoring/detections.py`, `spiderweb/remote_monitoring/adjudication.py` | Binding to asset, panel and comparison |
| B20 | Discrepancy classification | ABSENT | — | All of it |
| B21 | Gap intelligence | PARTIAL | `spiderweb/subsurface/residuals.py`, `gebco/marine_evidence.py` | Now a candidate taxonomy in `registry/geo_sar/gap_taxonomy.json` |
| B22 | Coverage computation | PARTIAL | `scripts/source_adapters/sdk/core.py`, `scripts/grid_coverage_check.py` | Independent denominators (D08) |
| B23 | Segment review lifecycle | ABSENT | Closest: `tools/pr_dem_review_lock.py` | All of it |
| B24 | Qualification engine | ABSENT | Closest: `scripts/check_repo_readiness_policy.py` | All of it |
| B25 | Persistent supervisor | ABSENT before this work | Now `spiderweb/geo_sar/jobs.py` and `scripts/geo_sar_worker.py`; see D16 | Network retrieval handler, process supervision |
| B26 | Federation evidence binding | EXISTS | `federation/export_writer.py`, `federation/envelope.py`, `spiderweb/access_points/hub_export.py` | — |
| B27 | Security and publication | PARTIAL | `pipeline/path_safety.py`, `scripts/check_data_policy.py`, `.federation/check_admin_boundary.py` | See D15 for the open defects |
| B28 | API and event gateway | PARTIAL | `server/backend/main.py`, `server/backend/gis_api.py` | `/geo-sar` routes (D13) |

Jobs before this work lived in a dictionary in the API process
(`server/backend/main.py`); they did not survive that process.

## D11 — Frontend modules

The frontend is one React, TypeScript and Vite application in
`server/frontend`. It has no router and no state library. MapLibre resolves to
6.19.0 through the lockfile (`package.json` says `latest`); Cesium is pinned
to 1.147.0.

| ID | Module | State | Reuse |
|---|---|---|---|
| F01 | Programme overview | PARTIAL | `server/frontend/src/modules/CommandCenter.tsx` |
| F02 | Coverage map | PARTIAL | `server/frontend/src/modules/SpatialIntelligence.tsx` |
| F03 | Logical mosaic matrix | ABSENT | TanStack Table pattern in `server/frontend/src/modules/FinanceIntelligence.tsx` |
| F04 | Selection toolbar | PARTIAL | `server/frontend/src/modules/SpatialToolsPanel.tsx`, `server/frontend/src/modules/GisViewerControls.tsx` |
| F05 | Split-view workbench | PARTIAL | `server/frontend/src/spatial/imagery/CompareOverlay.tsx` (swipe only, one imagery family, one-way camera follow) |
| F06 | Reusable comparison panel | ABSENT | — |
| F07 | Cascading selectors | PARTIAL | `server/frontend/src/spatial/imagery/ImageryPanel.tsx` |
| F08 | Viewport synchronisation | PARTIAL | `server/frontend/src/spatial/runtime/SpatialRuntime.ts` (`getView`, `setView`) |
| F09 | Segment inspector | ABSENT | Pattern: `server/frontend/src/components/InspectorShell.tsx` |
| F10 | Source registry explorer | PARTIAL | `server/frontend/src/spatial/accessPoints/SourceCoveragePanel.tsx` |
| F11 | Dataset version explorer | ABSENT | — |
| F12 | Native asset ledger | ABSENT | — |
| F13 | Acquisition console | ABSENT | Server-sent event client in `server/frontend/src/api/client.ts` |
| F14 | Original evidence explorer | PARTIAL | `server/frontend/src/spatial/accessPoints/AccessPointDetail.tsx` |
| F15 | Temporal review | PARTIAL | `server/frontend/src/components/Timeline.tsx` |
| F16 | Comparison results table | ABSENT | TanStack Table pattern |
| F17 | Observation and annotation | ABSENT | — |
| F18 | Gap atlas | ABSENT | — |
| F19 | Gap registry | ABSENT | — |
| F20 | Segment review queue | ABSENT | Layout of `server/frontend/src/modules/AnomalyWorkbench.tsx` |
| F21 | Qualification dashboard | ABSENT | — |
| F22 | Persistent execution console | PARTIAL | Pipeline log over server-sent events; not persistent |
| F23 | Federation evidence bindings | PARTIAL | `server/frontend/src/components/RelationshipGraph.tsx` |
| F24 | Resource and storage monitor | ABSENT | — |

Design system: hand-written CSS on `--fd-*` tokens
(`server/frontend/src/styles/federation.css`), light and dark, with side
panels becoming drawers below 768 px
(`server/frontend/src/styles/mobile-workbench.css`).

### Defects found that the workbench depends on

1. **Two writers disagree about the map URL fragment.** The imagery controller
   writes a three-part `#map=` value on every move; the viewer controls read
   and write a five-part value and reject anything else. A saved view loses
   bearing and pitch on the next pan. Synchronised viewports need one owner
   of view state first.
2. **The cartographic preset contract is not wired.**
   `server/frontend/src/spatial/config/cartographicPresets.ts` is imported
   only by its own test.
3. **Renderer versions differ across the Federation.** thehub-pr locks
   MapLibre 6.6.0 and Cesium 1.144.0 for its own frontend; this repository
   runs 6.19.0 and 1.147.0. The Federation workbench proposal asks for pinned
   versions.

## D01 — Capability summary against the directive

| Directive capability | State | Evidence |
|---|---|---|
| Canonical ledger of datasets, versions, files, footprints | PARTIAL | D02, D03; pilot ledger for 28 files |
| Footprint-based relationships, not filenames | PASS for the pilot | `tests/test_geo_sar_pilot.py`, four fixtures on real footprints |
| Register before download | PASS for the pilot | 28 assets registered, 0 acquired |
| Acquire once, reuse across segments | PASS at the ledger level only | `test_05_recovery_does_not_duplicate_mutations`; no provider retrieval yet |
| Comparison of versions | PARTIAL | One site-based comparison of the pilot's two versions exists in the elevation lane; no method qualified for segments; D07 |
| Discrepancy and gap records | PARTIAL | Six pilot gaps recorded; no lifecycle engine |
| Logical mosaic | OPEN | Specified in D09; not built |
| Split-view workbench | OPEN | Specified in D10; not built |
| Persistent execution | PARTIAL | D16: ten tests pass for local steps |
| Federation governance binding | BLOCKED | D14: no admission route exists for this job class |
