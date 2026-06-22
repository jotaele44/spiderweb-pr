# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Releases are cut by pushing a `v*` tag, which the `release` workflow turns into a
GitHub Release using the matching section below (T6-53).

## [Unreleased]

### Added
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

[Unreleased]: https://github.com/jotaele44/spiderweb-pr/commits/main
