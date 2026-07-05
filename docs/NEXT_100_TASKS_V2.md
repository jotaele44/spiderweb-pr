# Next 100 Tasks (V2)

Second optimization & upgrade sweep for `spiderweb-pr`. This supersedes the
first sweep in [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md) (Tier 1–Tier 5 +
Workstream B + Cross-workstream, ~29/38 complete per the
[ROI Task Ledger](ROI_TASK_LEDGER.md)). It carries the still-open items forward,
folds in the packaging/cohesion findings from [`../RECOMMENDATIONS.md`](../RECOMMENDATIONS.md),
and adds optimization categories the repo had not yet planned: performance/scale,
observability, security, typing/CI parity, and dependency-extras packaging.

Each row carries **one-line scope + estimated engineer-hours + blockers**, so an
operator can pick up any item independently. Estimates assume existing test
scaffolding is reused and carry ±50% uncertainty.

The three **P0 quick-wins** were executed in the same PR that introduced this
doc and are marked ✅ below for traceability.

---

## P0 — executed in this sweep

| # | Task | Result |
|---|---|---|
| **P0-1** | ✅ Fix packaging identity | `pyproject.toml` renamed `gebco-bathymetry-pipeline` → `spiderweb-pr`; `packages.find` now ships `pipeline/fr24/integration/readiness/federation/server/scripts/gebco/earthgpt/llm` (was gebco-only). |
| **P0-2** | ✅ Reconcile dependency pins | `pyproject.toml` is the single source of truth for ranges; `requirements.txt` numpy/shapely aligned (was `numpy>=1.26` vs `>=2.4`); narrow `<x.(y+1)` caps relaxed to `<next-major`; exact pins remain in `constraints.txt`. |
| **P0-3** | ✅ Merge duplicate config dirs | `config/` (2 files) merged into the heavily-referenced `configs/`; 3 code refs + 1 docstring + 1 doc updated; empty `config/` removed. |

---

## Theme 1 — Packaging & dependency hygiene

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **1** | Optional-dependency extras | Add `[airspace] [gebco] [rag] [earthgpt] [server] [federation]` extras to `pyproject.toml`, mapping each subsystem's deps. | 3 h | None |
| **2** | Collapse requirements files | Reduce the 6 `requirements*.txt` to thin `-e .[extra]` shims. | 2 h | #1 |
| **3** | Document two-tier dep model | README/CONTRIBUTING note: ranges in `pyproject`, exact pins in `constraints.txt`. | 1 h | #1 |
| **4** | Console entry points | `[project.scripts]` for `run_all`, `release_check`. | 1 h | P0-1 |
| **5** | Typing/packaging markers | Add `py.typed` + package-data declarations. | 1 h | None |
| **6** | CI install matrix | `pip install .[extra]` import-smoke per extra in CI. | 2 h | #1 |
| **7** | Upper-bound audit | Repo-wide pass relaxing remaining narrow caps; verify against `constraints.txt`. | 2 h | P0-2 |

## Theme 2 — Schema & validation contracts

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **8** | N1 release_report schema | `schemas/release_report.schema.json` + register in `schema_index.json`. | 1 h | None |
| **9** | N2 integration_report schema | `schemas/integration_report.schema.json` + validate in `release_check.export_pr_intel`. | 1 h | None |
| **10** | N3 RLSM CSV schemas | One JSON Schema per the 14 RLSM CSV outputs; register all. | 3 h | None |
| **11** | T2-18 geometry validity | `validate_geometry(features)` on `SchemaValidator` (shapely), enforced on GeoJSON exports. | 3 h | shapely (already a dep) |
| **12** | T2-19 null-field policy | Reject `null` for required cols → enriched review queue (`error_type='null_field'`). | 2 h | None |
| **13** | T2-20 confidence-scale tests | Assert every `confidence` ∈ `[0,1]` + HIGH/MED/LOW/REJECTED label. | 2 h | None |
| **14** | Envelope schema | JSON Schema for `federation/envelope.py` + explicit version assertion. | 2 h | None |
| **15** | Contract-Finance golden fixture | Golden schema fixture for Contract-Finance v1.2.0 to detect producer-side breaks. | 2 h | None |
| **16** | schema_index coverage test | Test that every indexed artifact resolves to a real schema file. | 1 h | None |
| **17** | federation.json schema | JSON Schema for the discovery manifest. | 1 h | None |
| **18** | Example-artifact CI gate | Validate all checked-in example artifacts against registered schemas. | 2 h | #8–#10 |

## Theme 3 — Spiderweb language (remaining T3)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **19** | T3-26 MBIL expansion | Extend MBIL scoring to native POI + corridor records in the producer. | 3 h | None |
| **20** | T3-28 AASB corridor flag | `aasb_mbil_corridor_flag` per edge in `aasb_airspace_edges.csv`. | 1 h | #19 |
| **21** | T3-29 overlay carry | Carry the AASB flag into `spiderweb_overlay`. | 30 m | #20 |
| **22** | T3-30 / T5-45 terrain hook | Stub terrain-elevation lookup interface + documented API. | 4 h | DEM source decision |
| **23** | Additive-field regression tests | Tests for the 5 fields landed in PR #63. | 1 h | None |

## Theme 4 — Performance & scale

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **24** ✅ | N5 `--workers` for rlsm_unlabeled | **Done (#129)** — injectable mini-batch ThreadPool harness; tesseract is a subprocess, so OMP pinning (not ProcessPool) is the real lever — added in the post-V2 tidy PR. | 2 h | None |
| **25** ✅ | SQLite index audit | **Done** — covering indexes in Theme 4; watchlist-scan index extended in #127. | 2 h | Migration |
| **26** ✅ | Bulk-insert batching | **Done** — `executemany` in Theme 4; flight track-point inserts batched in #127. | 2 h | None |
| **27** | WAL + tuned PRAGMAs | Enable WAL + cache/synchronous tuning on the flight DB. | 1 h | None |
| **28** | Profile operational_intelligence | Profile the 35 KB hottest module; optimize hotspots. | 4 h | None |
| **29** | Vectorize adapter loops | Replace `iterrows` with vectorized/`itertuples` in adapters. | 3 h | None |
| **30** ✅ | Cache OCR engine init | **Done (#129)** — the OCR engine is built once (`_OCRWorker(fa.ocr)`) and reused across every `process()` call. | 2 h | None |
| **31** | Parquet export option | Optional pyarrow Parquet for the large CSV exports. | 2 h | None |
| **32** | Chunked reads | Lazy/chunked reads for the 500k-candidate tables. | 3 h | None |
| **33** | Memoize centroid distances | Cache municipal-centroid distance (T3-24 path). | 1 h | None |
| **34** | Per-stage benchmark | Record per-stage wall-clock into `release_report.json`. | 2 h | None |
| **35** | Incremental export | Hash-gate: re-emit only artifacts whose inputs changed. | 4 h | None |

## Theme 5 — Testing & coverage

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **36** | Tier 6 #21 test_release_check | Cover the 6-stage gate. | 2 h | None |
| **37** | Tier 6 #22 test_run_modes | Cover strict/demo/normal resolver. | 1 h | None |
| **38** | Tier 6 #23 test_provenance_utils | Cover the 8-key metadata block + git fallback. | 1 h | None |
| **39** | Tier 6 #26 spiderweb_intake ext | Tests for the new additive fields. | 2 h | #23 |
| **40** | N6 / B7 harden reproducibility | "Two fresh exports" instead of on-disk-vs-fresh. | 30 m | None |
| **41** ✅ | B-integrate RLSM into suite | **Done (#129)** — `--rlsm-status` on `run_all.py`; `tests/test_rlsm_unlabeled.py` in the default suite. | 3 h | None |
| **42** ✅ | Coverage + ratchet | **Done** — `pytest-cov` floor in CI (Theme 5); raised 55→64 in the post-V2 tidy PR (TOTAL 66.13%). | 2 h | None |
| **43** | Property-based tests | hypothesis for OCR-confidence + geometry parsers. | 3 h | None |
| **44** | Resolve ignored suites | Fix or document `test_io` / `test_terrain` exclusions. | 2 h | None |
| **45** | GeoJSON golden-file tests | Golden shape per GeoJSON export. | 3 h | #57 |
| **46** | Flaky-test quarantine | Seed-fixed RNG + quarantine marker. | 2 h | None |
| **47** | Smoke fixture DB | Commit a tiny fixture DB so `smoke` runs in CI. | 2 h | None |

## Theme 6 — CI/CD & developer experience

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **48** | Expand pre-commit | Add eof-fixer, yaml-lint to the existing ruff+black hooks. | 1 h | None |
| **49** | Introduce mypy | Gradual per-package typing + CI type-check job. | 4 h | #5 |
| **50** | CI parity | lint + type + test + release-check matrix (parity with moneysweep-pr). | 3 h | #49 |
| **51** | CI caching | Cache pip + model downloads. | 1 h | None |
| **52** | Dependency-refresh workflow | dependabot or scheduled cron PR. | 1 h | None |
| **53** | Release tagging | Tag workflow + CHANGELOG generation. | 2 h | None |
| **54** | Workflow hardening | `concurrency` cancel-in-progress + path filters. | 1 h | None |
| **55** | README badges | CI + coverage status badges. | 30 m | #42 |
| **56** | Makefile bootstrap | `make bootstrap` → venv + extras + pre-commit install. | 1 h | #1 |

## Theme 7 — GIS / export upgrades

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **57** | T5-41 GeoJSON `_meta` bag | Common `_meta` Feature sub-object (`source_artifact`, `produced_at`, `producer_module`). | 2 h | None |
| **58** | T5-42 KML export | `_export_kml` via `simplekml` (optional dep). | 2 h | simplekml |
| **59** | T5-43 corridor labels | Map scores to operator-facing labels. | 3 h | None |
| **60** | T5-44 centroid input hook | Operator-supplied centroid CSV instead of hardcoded 72-municipality list. | 2 h | None |
| **61** | T5-46 QGIS `.qml` pack | Ship style files referenced by `GIS_EXPORT_GUIDE.md`. | 2 h | None |
| **62** | T5-47 map-preview PNGs | Headless matplotlib/contextily preview per GeoJSON. | 3 h | None |
| **63** | T5-49 deprecate ogr2ogr | Remove the KML workaround once #58 native KML lands. | 30 m | #58 |
| **64** | GeoPackage export | Single-file `.gpkg` export option. | 2 h | None |
| **65** | CRS/EPSG stamping | Stamp CRS metadata on every geo artifact. | 1 h | #57 |

## Theme 8 — RLSM pipeline upgrades

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **66** | N4 canonicalize recover-tails | Move rescue logic into `scripts/rlsm_recover_tails_by_rawtext.py`; emit `processing_runs` row. | 2 h | None |
| **67** | B-dedup-unique index | UNIQUE on `aircraft_observations(screenshot_id, registration, source_zone)`. | 1 h | Migration |
| **68** | B-flight-track v2 | Pixel CV: `track_length_px`, `bbox_*`, `has_loop/orbit/gap`. | 6 h | #69 |
| **69** | B-geo-anchors v2 | Per-screenshot derived anchors via OCR-matched POIs → RANSAC homography. | 8 h | None |
| **70** | OCR-failure JSONL | Export `ocr_status='failed'` rows as a flat JSONL for operators (T4-32). | 1 h | None |
| **71** | Coverage drift section | Per-zone + per-engine drift in `rlsm_coverage_report.md`. | 2 h | None |
| **72** | Confidence recalibration | Recalibrate OCR confidence against labeled ground truth. | 4 h | Labeled set |
| **73** | Ensemble vote | Multi-engine vote for low-confidence OCR cells. | 4 h | Engines installed |

## Theme 9 — Federation hardening

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **74** ✅ | Contract-compat CI test | **Done** — golden envelope + version-pin test (Theme 9); canonical-export contract golden added in #128. | 2 h | #15 |
| **75** | live_execution gate | Criteria + test for flipping `federation.json` live-execution to true. | 3 h | None |
| **76** | Hub-query spatial index | Pagination + rtree spatial index in the hub query path. | 4 h | rtree |
| **77** | Version negotiation | Envelope schema-version negotiation handshake. | 3 h | #14 |
| **78** | Correlation fixtures | Cross-producer external-id correlation test fixtures. | 2 h | None |
| **79** | Export dry-run + diff | Dry-run + diff mode for federation export. | 2 h | None |

## Theme 10 — Observability & robustness

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **80** | Structured logging | Central logging config + JSON formatter across runners. | 3 h | None |
| **81** | Error taxonomy | Replace bare excepts; introduce a typed error taxonomy in the pipeline. | 3 h | None |
| **82** | Verbosity + progress | `--verbose/--quiet` + progress bars on long runners. | 2 h | None |
| **83** | Server health-check | Health endpoint + DB integrity check in `server/`. | 2 h | None |
| **84** | Checkpoint/resume | Checkpoint files for multi-hour runs. | 3 h | None |
| **85** | Central config loader | Schema-validated YAML loader for `configs/*.yaml`. | 3 h | None |
| **86** | Seed enforcement audit | Audit deterministic seeding across stochastic steps. | 2 h | None |

## Theme 11 — Security & data policy

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **87** | pip-audit in CI | Dependency vulnerability scan. | 1 h | None |
| **88** | Secrets scan + .env.example | Secrets scan; confirm no creds; add `.env.example`. | 1 h | None |
| **89** | Data-policy lint | Enforce `DATA_POLICY.md` redaction rules on exports. | 3 h | None |
| **90** | Path-traversal review | Sanitize file-ingest paths. | 2 h | None |
| **91** | SQL parameterization audit | Confirm no f-string SQL across the codebase. | 2 h | None |
| **92** | License audit | Add `LICENSE` / SPDX headers if missing. | 1 h | None |

## Theme 12 — Docs & structure

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **93** | docs index | `docs/README.md` grouping the 50+ docs by subsystem (RECOMMENDATIONS #6). | 2 h | None |
| **94** | ARCHITECTURE refresh | Update for federation + RLSM-canonical status. | 1 h | None |
| **95** | Propagate package rename | Update all docs referencing the old package name (post-P0-1). | 1 h | P0-1 |
| **96** | Per-subsystem READMEs | READMEs for `gebco/`, `earthgpt/`, `llm/` prepping the split decision. | 2 h | None |
| **97** | Monorepo-split evaluation | Decision doc + extras boundary (RECOMMENDATIONS #5). | 4 h | #1 |
| **98** | Consolidate FR24 docs | Merge the `FR24_*.md` set into one guide with a TOC. | 3 h | None |
| **99** | API reference | Generate pdoc/mkdocs reference for public modules. | 3 h | None |
| **100** ✅ | Roadmap maintenance | **Done (this PR)** — post-V2 PRs recorded in `ROI_TASK_LEDGER.md`; roadmap + ledger linked from README. | 1 h | None |

---

## Effort summary

| Theme | Open tasks | Estimate |
|---|---|---|
| 1 — Packaging & deps | 7 | ~12 h |
| 2 — Schema & validation | 11 | ~20 h |
| 3 — Spiderweb language | 5 | ~9.5 h |
| 4 — Performance & scale | 12 | ~28 h |
| 5 — Testing & coverage | 12 | ~23.5 h |
| 6 — CI/CD & DX | 9 | ~14.5 h |
| 7 — GIS / export | 9 | ~17.5 h |
| 8 — RLSM pipeline | 8 | ~28 h |
| 9 — Federation | 6 | ~16 h |
| 10 — Observability | 7 | ~18 h |
| 11 — Security & data policy | 6 | ~10 h |
| 12 — Docs & structure | 8 | ~17 h |
| **Total** | **100** | **~214 h** |

## Recommended sequencing

1. **Themes 1–2 first** — packaging extras + the remaining schemas unblock clean installs and close the validation contract gaps.
2. **Themes 4 + 5 + 6** are the highest-ROI next sweep — performance wins (the `--workers` and indexing items pay back immediately) land alongside the test/CI hardening that protects them.
3. **Themes 9 and 11** protect the two boundaries the project is most exposed on: the cross-repo federation contract and security/data-policy.
4. **Theme 12 (#97 monorepo split)** is the one strategic decision; sequence it after #1 so each split candidate already has a clean extras boundary.

## Cross-references

- [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md) — the prior (first) sweep this supersedes.
- [`ROI_TASK_LEDGER.md`](ROI_TASK_LEDGER.md) — running scorecard; migrate completed V2 items here.
- [`../RECOMMENDATIONS.md`](../RECOMMENDATIONS.md) — packaging/cohesion findings folded into Themes 1 & 12.
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md) — the gate this work is gated against.
- [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) / [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md) — contracts Themes 2 & 3 extend.
