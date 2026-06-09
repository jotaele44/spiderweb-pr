# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Releases are cut by pushing a `v*` tag, which the `release` workflow turns into a
GitHub Release using the matching section below (T6-53).

## [Unreleased]

### Added
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
