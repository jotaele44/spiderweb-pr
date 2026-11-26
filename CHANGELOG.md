# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Releases are cut by pushing a `v*` tag, which the `release` workflow turns into a
GitHub Release using the matching section below (T6-53).

## [Unreleased]

### Added
- Every gridded DEM compared against 3DEP 1 m lidar at eight stratified sites
  (`docs/sources/dem_lidar_comparison.md`, `scripts/run_dem_vs_3dep_lidar.py`, sites
  in `data_sources/elevation/lidar_comparison_tiles.json`, receipt under
  `evidence/dem_sources/lidar_comparison_2026-11-26/`). Lidar is averaged onto each
  DEM's own grid and moved to its datum through its survey's own geoid (GEOID12B for
  2018, GEOID18 for D24), a NAD83(2011) to ITRF2014 Helmert at the survey epoch and
  EGM96 or EGM2008. Median DEM minus lidar: NASADEM +1.86 m, SRTMGL1 +3.61 m, AW3D30
  +4.14 m, COP30 +4.38 m, CUDEM 1/9" -0.02 m; D24 minus 2018 lidar -0.14 m as
  published and -0.15 m on one geoid. The conflict checker gains an `abs_at_most`
  check. The 2018 3DEP product is now `usgs_3dep_1m_pr_prvi_2018` (TNM projects
  PR_PRVI_A_2018 to PR_PRVI_H_2018).
- Each 3DEP survey's geoid realization, from its own project metadata
  (`scripts/check_3dep_vertical_realization.py`, receipt under
  `evidence/dem_sources/3dep_vertical_realization_2026-11-26/`): 2018 is PRVD02
  through GEOID12B (vendor FGDC metadata of blocks A, D, E, F, H), D24 is PRVD02
  through GEOID18 (LPC reports of all six parts). The catalog now records PRVD02
  with a new optional `geoid_model` for the 2018 and D24 DEMs and the 2018 point
  cloud, keeps the NAVD88 wording as stated, and holds conflict
  `3dep_vertical_datum_label` open. At USGS's 91 D24 checkpoints, D24 is -0.006 m
  (median) and 2018 on a GEOID18 basis +0.029 m. The merge policy keeps products on
  one datum but different geoids in one group as separate layers
  (`same_datum_separate_geoid_layers`, with `layer_groups()`), so their difference
  stays measurable.
- DEM sources broken down by acquisition platform
  (`docs/sources/dem_sources_by_platform.md`). The catalog
  `data_sources/elevation/dem_platform_catalog.yml` holds 30 products in four
  classes (spaceborne, airborne, shipborne, compiled). All 71 elevation
  registrations in 22 files are accounted for as aliases or classified
  non-products, and six conflicts between registries are recorded.
  `source_adapters/dem_platform` adds the merge policy: sources stay in separate
  layers unless they share platform class, surface model and a declared vertical
  datum. Independence is decided on canonical acquisition roots.
- NASA SRTMGL1 v003 adapter (`source_adapters/nasa_srtmgl1`,
  `docs/source_adapters/nasa_srtmgl1.md`) for the six Puerto Rico tiles, fetched
  from LP DAAC with an Earthdata Login bearer token. Measured on 2026-11-23 from
  SRTMGL1N: 99.979% of land samples are SRTM radar measurements, with 1,668 ASTER
  fill samples and one NED fill sample. Receipt under
  `evidence/dem_sources/srtmgl1_pr_2026-11-23/`.
- OpenTopography Global DEM adapter (`source_adapters/opentopography_globaldem`,
  `docs/source_adapters/opentopography_globaldem.md`) for SRTMGL1, NASADEM, COP30
  and AW3D30. The API key is a query parameter, so it is redacted from every
  recorded URL. COP30 was fetched for Puerto Rico on 2026-11-23 (receipt under
  `evidence/dem_sources/cop30_pr_2026-11-23/`): 1 arc-second, EPSG:4326, no
  vertical CRS declared, heights up to 1,328.8 m at the Cerro de Punta summit.
  AW3D30 and NASADEM followed on 2026-11-24, and the four spaceborne DEMs were
  compared over SRTM land samples (`evidence/dem_sources/spaceborne_pr_2026-11-24/`):
  NASADEM differs from SRTMGL1 with a 1.754 m standard deviation, against
  4.854 m for COP30 and 4.602 m for AW3D30, as their shared Shuttle root predicts.
  COP30's vertical datum is now recorded as EGM2008 (ESA Copernicus DEM Product
  Handbook) and AW3D30's as EGM96 (OpenTopography distributor metadata; JAXA's
  document returned HTTP 404). Over Puerto Rico the two geoids differ by -0.95 to
  +1.09 m; receipt `evidence/dem_sources/vertical_datums_2026-11-24/`.

### Changed
- `tools/pr_dem_one_tile_pilot.py` refuses a tile whose native pixel is coarser
  than `--target-resolution-m`, unless `--allow-coarse-source` is given; the
  manifest records `native_resolution_m` and `coarse_source_override`.
  `tools/pr_dem_batch_runner.py` forwards the flag.

### Notes
- The NCCOS lead is closed. On 2026-11-23, under a grant of four metadata
  requests, NCEI's geoportal service returned the ISO records for accessions
  0131855 and 0128255; the landing-page route still returned HTTP 503. Neither
  stated bounding box contains the W00247 depressions or the 15 m object, so
  no grid was downloaded. 0131855's abstract names W00247, but its box lies
  north-east of Puerto Rico: a contradiction in the record, noted in
  `docs/ACCESS_POINT_REGISTRIES.md`. The two records are frozen under
  `evidence/access_points/real_survey/2026-11-23-nccos-metadata/`. No code or
  registry record changed.
- The NCCOS lead (NCEI accessions 0131855 and 0128255) was retried on
  2026-11-22 under a new grant of two metadata requests. Both failed with HTTP
  503, making seven failed requests in all. Nothing was frozen; the lead stays
  paused (`docs/ACCESS_POINT_REGISTRIES.md`). No code or data changed.
- The search for an independent second seabed survey has one lead left: NCCOS
  processed grids at NCEI (accessions 0131855 and 0128255). Five metadata
  requests on 2026-11-20 all failed (HTTP 503, 502, timeout), so nothing was
  learned or frozen; the lead is paused and recorded in
  `docs/ACCESS_POINT_REGISTRIES.md`. No code or data changed.

### Fixed
- The DEM vs 3DEP lidar comparison moved the 2018 lidar off PRVD02 with GEOID18
  (EPSG:9230), the geoid the D24 survey used, instead of the survey's own GEOID12B
  (EPSG:7646, which pyproj leaves out as superseded). It now picks each survey's
  operation from `stated_geoid`, and the comparison was re-run; the 2018 offsets
  changed by GEOID12B - GEOID18 (-0.08 to +0.13 m at the D24 checkpoints).
- Rerunning the SRTMGL1 or OpenTopography `fetch` no longer drops earlier records
  from the cache's `provenance.json`: cache hits keep their download time and host
  while the sha256 is unchanged, and records outside a narrower selection are kept
  (`source_adapters/cache_provenance.py`).
- **The hub's federation ingest could not run this repository's export.** Since
  the access-point lane was added to `export_canonical`, every thehub-pr ingest
  failed at "Fetch producers and run their exports" with `No module named
  'numpy'`. The hub runs the export with only its own packages, and the lane
  reached numpy and scipy through `gebco/__init__.py` and shapely through
  `spiderweb/subsurface/__init__.py`. Both packages now load those modules on
  first use, and `spiderweb/subsurface/evidence.py` imports shapely only for type
  checking. The exported records are unchanged. `tests/test_federation_export_hub_env.py`
  runs the `export_canonical` command with every base dependency the hub does not
  install blocked.
- The elevation-inventory adapter stored the inventory's HTML "link" fragments
  and prose as if they were addresses. It now cites only a real address and
  keeps the published field verbatim (`spiderweb/access_points/acquisition.py`).

### Changed
- **Nested basins are now the access-point detectors' default**, by the
  repository owner's decision after the comparison with the USGS karst map.
  The low-level delineation still nests only when asked; a declared survey run
  must now state `parameters.nested`; the run of 2026-11-17 is pinned to outer
  basins only and still reproduces. Nested basins now use the same depth floor
  as outer ones, so numerical residue on a rim is not counted as water.

### Added
- **Geospatial Visualization Engine (`viz_engine/`, fixture-only).** Renders a top-down
  map, a vertical cross-section and a bounded glTF 3D scene from frozen, sha256-pinned
  snapshots, with a machine-readable receipt per artifact and byte-reproducible
  output. Connections are drawn only according to their evidence class; validation
  gates (CRS/datum/unit mismatch, reversed flow, disconnected segments, missing raster
  coverage, unsupported connections, duplicate or merged IDs) mark a run `FAIL` and
  block publication export. Certified against a synthetic snapshot only; no real-data
  adapter and no production wiring. See `docs/GEOSPATIAL_VISUALIZATION_ENGINE.md`.
- **Access-point records exported to the federation hub**, by the repository
  owner's decision of 2026-11-20. `scripts/federation_export.py` gains an opt-in
  `--access-point-registries` lane (`spiderweb/access_points/hub_export.py`), and
  the `export_canonical` command in `federation.json` passes it. Records that are
  candidates or better (today 4 inland, 1 off-shore) become entities with a
  CANDIDATE, producer-local identity, an INTERPRETIVE class and, where their own
  observation states one, a representative point marked as having an assumed
  coordinate system; provisional seeds, detections and relationships are not
  exported. The producer entity schema gains three entity types and an optional
  `attributes` object. The hub's `validate-package` returns VALID for the
  production package; nothing reaches the hub until this is merged.
- **A search for an independent second seabed survey**
  (`spiderweb/access_points/replication.py`,
  `scripts/search_access_point_replication.py`). Two metadata requests and one
  37.8 MB download under the owner's grant. The one gridded survey whose
  catalogue box overlapped the depressions (NOS H12935, 2016) has no soundings
  within 11 km of them; the independent cruises whose footprints cross them hold
  raw pings only; the one processed grid nearby reaches nothing shallower than
  448 m. Outcome BLOCKED, recorded in a sealed report. A horizontal coordinate
  system with no EPSG code is now matched by its parameters, and the basis is
  recorded.
- **A seam test for depressions read from finer grids** (`survey.seam_test`),
  written before it was applied: narrow and grid-aligned, a level step across
  the axis along most of the length, and the step continuing past both ends.
  It finds a planted seam. Applied to both 8 m runs, it calls every outer
  depression NOT_SEAM_LIKE, including the 15 m object, whose earlier reading as
  a seam (from one profile) is withdrawn. Informational; no tier changes.
- **The seabed survey file read again from its finer grids.** A run may now
  state `resolution_m`; a variable-resolution survey file is then read from its
  finer grids resampled to that cell size (mean elevation and largest
  uncertainty of the nodes in each cell; empty where none; nothing
  interpolated). Every cell is recomputed from the nodes at extract time, and
  extract stops on any disagreement. Two runs at 8 m read the file already held
  (no download): all three base-grid depressions persist by a rule fixed in
  advance; 8 and 10 depressions are reported at the two declared area floors;
  one small steep object is flagged as a possible artefact. Runs can reuse another run's
  evidence and subset, and are compared with an earlier run; only
  `--set-current` moves the seabed pointer. No registry change.
- **First seabed survey through the access-point pipeline.** One gridded
  multibeam survey file (NOS W00247, file 3 of 4; 6.9 MB, fetched under an
  explicit grant of one file and held outside the repository) is read, bound to
  the tidal datum it states and searched for closed depressions
  (`spiderweb/access_points/bathymetry_run.py`,
  `scripts/process_access_point_seabed.py`, `seabed_runs` in
  `configs/access_point_survey_runs.yaml`). Its hash and statistics equal the
  August 2026 receipt for the same file. The run names no target record and
  states no position. It uses the product's own uncertainty for every cell and
  reports what that hides: over 56% of the covered cells a 2 m depression could
  not be reported. Three shallow, flat-floored depressions (2.8 to 6.5 m) were
  found in the 64 m base grid; they are shapes, classed EXPLORATORY, and none
  is attached to a record. Only the base grid is read; the file's finer grids
  are not. The file is registered in the Off-Shore registry as a held, hashed
  grid. No feature, observation or status changed and no seed gained a
  coordinate.
- **A second, optional rule for a single pit under a broad bowl**
  (`pit_area_jump`). It was measured on the same tile against the nested
  detector and did not help: 80 more objects, none of the three remaining
  mapped sinkholes recovered. It is off by default.
- **Nested basins in the access-point detector (opt-in).** A compound
  depression — several hollows sharing one rim — was reported as one basin. With
  `nested=True` the shared delineation (`spiderweb/access_points/raster.py`) also
  reports the basins inside it, each with its level, its parent and a depth that
  is a lower bound good to one step. Off by default: outer basins, identifiers
  and every committed report are unchanged. Compared against the USGS karst map
  on the same tile, with the reading rule fixed in advance, the share of mapped
  sinkholes reported as objects at 30 m rises from 32% to 61% while the
  displaced control rises from 16% to 28%; 70 of the 73 sinkholes that lay
  inside a larger basin are now reported. The object count triples. See
  sections 3 and 6 of `docs/ACCESS_POINT_SCIENTIFIC_METHOD.md`.
- **Comparison of the access-point detector with a published sinkhole map.**
  Reference maps are now held by the hash of their exact bytes and read only
  with a coordinate reference system bound to them
  (`spiderweb/access_points/reference.py`,
  `configs/access_point_reference_sets.yaml`); three were supplied by the
  repository owner and are committed. `validation.py` and
  `scripts/validate_access_point_detector.py` compare the closed-basin detector
  with 139 sinkholes the USGS Karst Map of Puerto Rico places inside the held
  elevation tile, at several depths and against a displaced control. The result
  is labelled REFERENCE_COMPARED, a new evaluation state that is never field
  accuracy: within the map's stated 100 m tolerance, 88% of mapped sinkholes
  are closed depressions at least 30 m deep (51% by chance), and the detector
  reports 32% of them as separate objects because it does not resolve basins
  nested inside a larger one. No threshold and no registry record changed. See
  section 6 of `docs/ACCESS_POINT_SCIENTIFIC_METHOD.md`.
- **Real-survey processing for the access-point registries.** A named survey
  product can now be fetched under its own grant that bounds files and bytes
  (`spiderweb/access_points/products.py`), read, bound to the vertical datum it
  states, and searched for closed basins (`survey.py`, `survey_run.py`,
  `scripts/process_access_point_survey.py`). One run is committed: two
  independent 1 m LiDAR elevation tiles over the registered point of
  `INAP-PR-000003`, fetched under an explicit owner grant (716 MB of an 800 MB
  ceiling; the tiles stay outside the repository, their hashes and a 1 km window
  are committed). 13 of 17 closed basins are seen by both surveys. A stated
  vertical datum is now checked for regional plausibility: both tiles say
  NAVD88, which is not realised in Puerto Rico. No registry record changed. See
  "Real-survey processing" in `docs/ACCESS_POINT_REGISTRIES.md`.
- **Planned source-discovery runs for the access-point registries.**
  `scripts/discover_access_point_sources.py` plans (offline), runs (only under
  an explicit grant) and re-checks (offline) a metadata-only query of the public
  survey catalogues over declared search boxes. Search boxes for the five
  off-shore seeds live in `configs/access_point_discovery_corridors.yaml`; a box
  says where to look and can never give a seed a position. A run keeps the exact
  response bytes and writes a sealed source catalogue, which
  `scripts/build_access_point_registries.py` now reads to register the listed
  surveys as references. One run was executed on 2026-11-16 under an explicit
  owner grant (48 requests, 180 surveys listed, exact responses kept); the
  registries now hold those surveys as citations. No survey product was
  downloaded and no feature, status or coordinate changed. See "Source
  discovery runs" in `docs/ACCESS_POINT_REGISTRIES.md`.
- **Inland and Off-Shore Access Point registries.** A new package,
  `spiderweb/access_points/`, holds two independent registries of candidate
  geographic features on one shared evidence foundation. Each record states,
  separately for existence, morphology, origin, physical opening,
  accessibility, function, connectivity and temporal validity, how well the
  claim is supported; the code keeps "anomaly", "feature", "opening", "passage"
  and "connection" apart and has no automatic promotion. Includes a
  vertical-datum contract, shared terrain and bathymetry processing with
  closed-basin delineation, typed relationships with path verification,
  cross-coastal transects, default-deny metadata discovery, and a read-only
  reader for other producers' exported packages. Read-only API under
  `GET /v1/access-points/*` (`server/backend/access_points_api.py`) and an
  Access points group on the Spatial map. The registries hold 5 candidate
  records crosswalked from the legacy node registry and 5 provisional
  off-shore records that carry no coordinates. Nothing is exported to the hub.
  The acronyms ILAP and OSAP already mean other things here and are not used
  as identifiers; see `docs/ACCESS_POINT_TERMINOLOGY_DECISION.md`. Start at
  `docs/ACCESS_POINT_REGISTRIES.md`.
- **Federation `source_monitors` stream (thehub-pr ADR 0013).**
  `scripts/federation_export.py` now writes `source_monitors.jsonl`. It has one row per
  source in `manifests/pr_hydrography/source_registry.csv` and
  `configs/missing_persons_sources.yaml`, and never one marked
  `federation_eligible: false`. Each row carries the declared status and cadence the Hub
  already showed, plus when the source last succeeded. That time is read only from run
  receipts in `data/source_run_state.json`. None exist yet, so every source is
  `NOT_RECORDED`. `prii-export-utils` is pinned to thehub-pr `0f62e4b` (0.2.0).
- **NOAA aerial imagery on the Spatial map.** The backend renders map tiles and
  image footprints from NOAA's public Emergency Response Imagery bucket
  (`noaa-eri-pds`) for 15 Puerto Rico / USVI flights — 2022 and 2024 pre-event
  baselines, Hurricane Maria and Hurricane Irma 2017 — registered in
  `configs/eri_imagery_sources.yaml` (`GET /imagery/eri/*`,
  `server/backend/eri_imagery.py`). The map gains a flight picker, opacity,
  image footprints with click-to-identify, swipe comparison between two flights,
  a base-map toggle, a scale bar, a cursor coordinate readout, and a URL
  fragment that restores the view. `VITE_TILE_URL`, previously defined but
  unused, now sets the base-map tiles. The `server` extra gains `rasterio` and
  `PyYAML`.
- **Road gazetteer: Puerto Rico route-numbering logic.** Canonical road rows now
  carry `route_number_band` (1–99 / 100–299 / 300–9999), `route_suffix` and
  `is_ramal`. Ramal aliases are generated, and DTOP rows whose declared network
  differs from the number band are flagged as LOW-severity
  `ROUTE_BAND_CLASS_DIVERGENCE` conflicts. New helpers `parse_route_ref` and
  `km_marker_from_text` are available to federation consumers. See
  `spiderweb_pr_road_name_gazetteer_ingest/docs/ROAD_NUMBERING_LOGIC.md`.
- **Cross-source missing-persons linkage (annotate-only):**
  `consolidate_missing_persons.py` now flags likely cross-source duplicates —
  rows sharing a deterministic blocking key (`sex|age_band|last_seen_municipio|
  last_seen_date`) across ≥2 sources get a stable `linkage_group_id` plus
  `linkage_keys_json` and a haversine `coord_disagreement_km`. Annotates rather
  than collapses (no fuzzy name matching; names are dropped at harvest), so the
  municipio aggregate's counts are unchanged and a distinct-people count can be
  layered on later. `linkage_group_id` is a consolidation-only output column
  (`CONSOLIDATED_COLUMNS`); the per-source harvester `CANONICAL_COLUMNS` contract
  is untouched.

### Fixed
- **Vertical-datum and evidence gates no longer accept placeholders.** In
  `gebco/marine_evidence.py`, a datum field holding "Not Provided", "User
  Specified" or similar no longer counts as a stated vertical reference, so
  two surveys that share only such a label can no longer be compared as if on
  one datum; and a direct observation with no acquisition root no longer ranks
  above one whose root is known. In
  `source_adapters/ncei_coastal_dem/datum_policy.py`, a selection whose datum
  is `source_dependent` now requires review instead of passing as "same datum".

### Changed
- **NWI wetlands layer made servable:** `ingest_reference_geo.py` now, by default,
  drops the huge offshore *Estuarine and Marine Deepwater* polygons and
  topologically simplifies (`shapely`, ~0.0001°) each kept NWI polygon — ~89% size
  reduction on coastal samples, bringing `wetlands_nwi_prvi` well under ~20 MB.
  New `--nwi-include-deepwater` / `--nwi-simplify-tol` flags; the manifest records
  `dropped_deepwater` / `simplify_tol` / `include_deepwater`.

### Added
- **Missing-persons layers wired + multi-source consolidation:** promoted
  `missing_persons_cases` + `missing_persons_by_municipio` to `WIRED` (the
  NamUs producer/emitter and its 15-test contract already existed), and added
  `scripts/consolidate_missing_persons.py` to merge the landed per-source
  redacted canonicals (NamUs + PRPB Amber/Rosa/Silver/Ashanti + Desaparecidos —
  all sharing `_harvest_base.CANONICAL_COLUMNS`) into a combined
  `data/sources/_consolidated/<date>/missing_persons_pr_canonical.csv`.
  `populate_dataset_layers.main()` now prefers the consolidated canonical over
  NamUs-only. Concat + within-source dedup by `case_id_hash`; cross-source
  identity linkage left for a later pass; raw PII stays git-ignored and only the
  municipio aggregate is federation-safe (`docs/DATA_POLICY.md`).
- **Reproducible live-source adapters for reference geographies:** added
  `server/ingestion/ingest_reference_geo.py`, fetching `nid_dams` (USACE National
  Inventory of Dams API), `gazetteer_pr_domestic_names` (USGS GNIS Domestic Names
  on the National Map S3 bucket), and `wetlands_nwi_prvi` (USFWS NWI ArcGIS
  service, tiled + paginated) directly from authoritative federal endpoints into
  servable `data/<layer>.geojson` + provenance manifests. Replaces reliance on
  undated operator-local GPKG snapshots and makes `wetlands_nwi_prvi` an
  actually-served layer (previously `reference_only`); registered in the `/geo`
  allowlist with `pipeline_wired: true`.
- **NOAA/NCEI coastal-DEM gaps closed:** resolved all six pending Puerto Rico
  1/3 arc-second MHW DEMs (Arecibo/Fajardo/Guayama/Mayagüez 2006+2007/Ponce) to
  live NGDC THREDDS OPeNDAP endpoints in `data_sources/noaa/ncei_coastal_dems.yml`
  (with `grid_shape` + `elevation_var`), generalized
  `scripts/acquire/noaa_ncei_opendap.py` to handle the `Band1`-vs-`z` elevation
  variable, and validated San Juan 2015 via a live raster sample (min -903.33 /
  max 120.99) — closing GAP_002 and GAP_003 and advancing San Juan to
  `source_raster_validated`. GAP_001 (PR-wide 2017 DEM) confirmed still
  unpublished in the live catalog.
- **Admin geographies promoted to WIRED:** the five TIGER/Line administrative
  layers (`municipios`, `tracts`, `places`, `barrios`, `puma`) now carry
  `pipeline_wired: true` in `configs/layer_catalog.yaml` and are flagged `WIRED`
  in the pin registry + taxonomy (they have a real producer, `ingest_tiger_pr.py`),
  moving the registry to WIRED 55 / GHOST 24 / PLANNED 2.
- **Census geo sources wired into the vector pipeline:** implemented the
  contract-tested TIGER/Line ingestor `server/ingestion/ingest_tiger_pr.py`,
  producing PR administrative-geography GeoJSON (`municipios` 78, `tracts`,
  `places`, `barrios`, and a new `puma` layer) from the
  `www2.census.gov/geo/tiger/TIGER2025/` directory, with a dual-provenance
  `data/tiger/2025/manifest.json` and a site→municipio/tract GEOID join. Added a
  `geo` install extra (geopandas/pyogrio/requests), registered `puma` in the
  layer catalog and `/geo/{layer}.geojson` allowlist, and bumped the Census
  Partnership shapefile adapter default to the `partnership25v2` vintage.
- **Post-V2 sweep (civic-data & hardening):** dataset layers / POI groups / ILAP
  types (#120); missing-persons + geodata source ingestion — harvesters, PR
  geocoder, layers (#123); FR24 ground-truth track harvest removed (migrated to
  skywatcher-pr) (#124); Head Start civic-layer schema contract (#125); batched
  flight track-point inserts + watchlist-scan index (#127); canonical-export
  contract golden test (#128); parallel unlabeled-RLSM runner + `run_all
  --rlsm-status` (#129); `federation/namespace.py` added to the lint/type
  allowlist (#130). Roadmap, ledger, and changelog reconciled against `main`
  (Theme 12 #100).
- **Theme 12 — Docs & structure:** subsystem-grouped `docs/README.md` index
  (#93); ARCHITECTURE status refresh for federation + RLSM-canonical (#94);
  per-subsystem `gebco`/`earthgpt`/`llm` READMEs (#96); monorepo-split decision
  doc (#97); consolidated `docs/FR24_GUIDE.md` TOC (#98); `docs/API_REFERENCE.md`
  (pdoc) (#99); roadmap Themes 2–12 migrated into `ROI_TASK_LEDGER.md` with the
  roadmap/ledger/changelog linked from the README (#100).
- **Theme 11 — Security & data policy:** advisory `pip-audit` CI job (#87);
  `.env.example` + a committed-secrets scan test (#88); `pipeline/path_safety.py`
  (`safe_join`/`is_within` path-traversal guards) (#90); an SQL-parameterization
  audit test asserting no `%`/`.format()`-built SQL (#91). (#92 license selection
  deferred — an owner decision; #89 data-policy lint deferred.)
- **Theme 10 — Observability & robustness:** central structured logging
  (`pipeline/logging_config.py`, JSON formatter) wired into `run_all.py` with
  `--verbose`/`--quiet`/`--log-json` (`pipeline/verbosity.py`) (#80, #82);
  schema-light central YAML config loader (`pipeline/config_loader.py`) (#85);
  deterministic global seeding (`pipeline/seeding.py`) + autouse test seed
  fixture (#86); `/health` endpoint now runs a SQLite integrity check and
  reports table count (#83). New modules added to the CI lint/type allowlist.
- **Theme 9 — Federation hardening:** committed golden envelope fixture
  (`tests/fixtures/envelope_v1_0.golden.json`) + a contract-version pin test
  (#74); `federation/readiness.py` encoding the live-execution gate criteria
  with tests (#75); cross-producer external-id (UEI) correlation fixtures and
  tests exercising `correlate_by_external_id` (#78); `--dry-run` and
  `--diff-from` modes for `scripts/federation_export.py` (#79).
- **Theme 8 — RLSM pipeline upgrades:** `ocr_failures.jsonl` operator export
  (flat JSONL of every `ocr_status='failed'` screenshot); per-zone and
  per-engine OCR coverage/drift sections in `rlsm_coverage_report.md`.
  (#66 recover-tails `processing_runs` emission and #67 `ix_air_dedup`
  unique index were already in place — verified, no change.)
- **Theme 7 — GIS / export upgrades:** per-feature `_meta` block on every ILAP
  GeoJSON feature; explicit `epsg: 4326` on FeatureCollections and CRS/EPSG
  stamps on the AASB manifest; operator-facing `corridor_label` on corridors;
  operator-supplied centroid CSV hook (`SPIDERWEB_CENTROID_CSV` +
  `set_municipal_centroids`); dependency-free native KML export (`.kml` sibling
  per GeoJSON, replacing the ogr2ogr workaround); QGIS `.qml` style pack under
  `styles/`.
- **Theme 6 — CI/CD & developer experience:** `lint` CI job (ruff + black + mypy)
  on a curated, gradually-growing allowlist; `concurrency` cancellation and
  docs-only `paths-ignore` on CI; Dependabot (pip + github-actions); tag-driven
  release workflow + this changelog; README status badges; pre-commit
  file-hygiene hooks; `make bootstrap`/`format`/`mypy`/`check`/`help` targets.
- **Theme 5 — Testing & coverage:** `pytest-cov` coverage ratchet
  (`--cov-fail-under=55`) on the core packages; two-fresh-export reproducibility
  tests for the ILAP/AASB exporters; populated-DB coverage of the release gate.
- **Theme 4 — Performance & scale:** `pipeline/db_utils.configure_connection()`
  (WAL + tuned PRAGMAs); covering indexes on the flight DB; `executemany`
  batch inserts in the RLSM extractors; `lru_cache` on `mbil_class()`;
  per-stage `elapsed_sec` in `release_report.json`; parallel-workers default
  for `rlsm_unlabeled`.
- **Theme 3 — Spiderweb language:** shared `integration/mbil.py`; `mbil_class`
  on POI/corridor candidates; `aasb_mbil_corridor_flag` edge column; terrain
  hook (`pipeline/terrain_hook.py`).
- **Theme 2 — Schema & validation contracts:** `federation_manifest` JSON
  Schema; `CONTRACT_VERSION` constant; example-artifact schema CI gate.

### Changed
- Coverage ratchet floor raised **55 → 64** (`--cov-fail-under` in CI); the core
  suite measures 66.13% TOTAL, leaving ~2pp headroom.
- **`poi` → `pin` migration (stage 3b):** the spiderweb candidate export artifacts
  were renamed `airspace_poi_candidates.geojson` → `airspace_pin_candidates.geojson`
  (+ its `.kml` sibling and `styles/*.qml`) and `poi_candidates.geojson` →
  `pin_candidates.geojson`, across producers, consumers, `schemas/schema_index.json`,
  and the export-contract docs. Feature properties (`poi_a`/`poi_b`,
  `candidate_type: "poi"`) and the deferred RLSM `*_pois` schema family are
  unchanged.
- **`poi` → `pin` migration (stage 2 — RLSM schema family):** `labeled_pois` →
  `labeled_pins`, `unlabeled_poi_candidates` → `unlabeled_pin_candidates` (schema
  `$id`, filename, `schema_name` in `schema_index.json`, artifact paths); column names
  `poi_id` → `pin_id`, `poi_type_guess` → `pin_type_guess` across `labeled_pins`,
  `unlabeled_pin_candidates`, and `ocr_normalized_labels` schemas;
  `labeled_poi_low_conf` → `labeled_pin_low_conf` in `manual_review.schema.json`
  enum. skywatcher-pr updated in parallel to emit the renamed output files and columns
  (internal skywatcher SQL table/column names are a separate deferred migration).

[Unreleased]: https://github.com/jotaele44/spiderweb-pr/commits/main
