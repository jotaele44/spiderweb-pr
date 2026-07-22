# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Releases are cut by pushing a `v*` tag, which the `release` workflow turns into a
GitHub Release using the matching section below (T6-53).

## [Unreleased]

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
