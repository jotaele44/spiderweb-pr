# ROI Task Ledger

Running scorecard for all release-readiness work. Each row records: task ID, name, ROI tier, status (`complete` / `partial` / `blocked` / `not_started`), files touched, tests added, validation command, result, blockers, next step.

This is the **planning artifact** operators update as work proceeds. Last updated **2026-06-01**.

For backlog beyond this scorecard, see [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md).

---

## Tier 1 — Release gate + reproducibility (complete)

| # | Task | Status | Files | Tests | Validation | Result |
|---|---|---|---|---|---|---|
| 1 | `provenance_utils.py` reproducibility helpers | ✅ complete | `provenance_utils.py` | (Tier 6 D2) | `pytest tests/` | All 8 metadata keys produced; git fallback works |
| 2 | `run_modes.py` strict/demo/normal resolver | ✅ complete | `run_modes.py` | (Tier 6 D2) | `pytest tests/` | `ModeResolution` + `assert_production_input` + `label_*` |
| 3 | `release_check.py` umbrella gate | ✅ complete | `release_check.py` | (Tier 6 D2) | `release_check --skip-tests` PASS | 6-stage defensive gate writes `release_report.json` |
| 4 | `run_all.py` CLI flags | ✅ complete | `run_all.py` | manual `--help` | `python run_all.py --help` shows the 4 new flags | `--release-check` / `--release-output-dir` / `--strict-production` / `--demo` |
| 5 | PR Intel adapter — determinism + provenance | ✅ complete | `integration/pr_intel_adapter.py` | `tests/test_pr_intel_adapter.py` | byte-identical exports across two runs | 8 data files identical; geo summary + reproducibility in manifest |
| 6 | AASB bridge manifest enrichment | ✅ complete | `integration/aasb_airspace_bridge.py` | `tests/test_fr24_bridge.py` | `pytest tests/test_fr24_bridge.py` | Reproducibility + per-file bbox |
| 7 | Spiderweb intake manifest enrichment | ✅ complete | `readiness/spiderweb_intake.py` | `tests/test_spiderweb_intake.py` | `pytest tests/test_spiderweb_intake.py` | Gap audit carries reproducibility; overlay has summary |
| 8 | Schema validation review queue enrichment | ✅ complete | `integration/schema_validation.py`, `tests/test_schema_validation.py` | extended | 4→9 cols, per-error rows, dedup, atomic write |
| 9 | PRII readiness — release_report link | ✅ complete | `readiness/prii_readiness_engine.py` | `tests/test_prii_readiness_engine.py` | non-breaking `release` key in report |
| 10 | `Makefile release-check` target | ✅ complete | `Makefile` | `make -n release-check` shows the right command | `make release-check` → runs `run_all.py --release-check` |

**Tier 1 verification:** 778 passed, 26 skipped, 0 failed on `pytest tests/ -q --ignore=test_io --ignore=test_terrain`. Release gate runs end-to-end against `~/flight_database.db` with `overall_status: PASS`.

---

## Tier 2 — Schema + validation contracts (complete)

| # | Task | Status | Files | Tests | Validation | Result |
|---|---|---|---|---|---|---|
| 11 | `schemas/schema_index.json` | ✅ complete | `schemas/schema_index.json` | `tests/test_schema_validation.py` (4 new) | `pytest tests/test_schema_validation.py` → 22 passed | 34 artifacts indexed across 5 workstreams |
| 12 | `docs/SCHEMA_AND_EXPORT_CONTRACTS.md` | ✅ complete | `docs/SCHEMA_AND_EXPORT_CONTRACTS.md` | doc-only | manual review | Per-workstream tables + reproducibility/null/confidence policies + add-new-artifact recipe |

---

## Tier 3 — Spiderweb language bridge (partial)

| # | Task | Status | Files | Tests | Validation | Result / Blocker |
|---|---|---|---|---|---|---|
| 13 | Additive Spiderweb fields | ⬜ not started | `readiness/spiderweb_intake.py` | (planned) | (planned) | 5 fields per D5: `fact_status`, `spiderweb_role`, `access_assertion_level`, `nearest_municipal_boundary_m`, `aasb_mbil_corridor_flag` |
| 14 | `docs/SPIDERWEB_LANGUAGE_BRIDGE.md` | ✅ complete | `docs/SPIDERWEB_LANGUAGE_BRIDGE.md` | doc-only | manual review | Canonical terminology + MBIL math + evidence tiers + alias map + field-by-field |

---

## Tier 4 — FR24 touchpoints — **SUPERSEDED BY RLSM** (DG-2 resolved)

**Decision (DG-2): RLSM is canonical.** The RLSM pipeline (parallel OCR runner, recover-tails canonicalization, `processing_runs` ledger, `outputs/rlsm_coverage_report.md`, schema-pinned `ocr_observations.engine`/`engine_version`/`psm`) collectively replaces `fr24/batch_run.py`'s functionality. See `docs/NEXT_100_TASKS.md` Tier 4 section for the original-task → RLSM-replacement mapping.

| # | Task | Status | Files | Tests | Validation | Result |
|---|---|---|---|---|---|---|
| 15 | FR24 batch runner hardening (`--dry-run`/`--offset`/failure log) | ✅ superseded | RLSM runners (`fr24.rlsm_ocr_parallel`, `fr24.rlsm_unlabeled`, etc.) | covered by `tests/test_rlsm_pipeline.py` | RLSM 10/10 tests pass | All sub-features delivered via RLSM (T4-31..T4-40 mapped 1:1) |
| 16 | `fr24/screenshot_inventory.py` status enum | ✅ vocabulary defined | RLSM `screenshots.ingest_status` + `.ocr_status` columns | `tests/test_rlsm_pipeline.py::test_screema_tables_exist` | DB schema is canonical | Legacy CSV path tolerated; new producers write to SQLite |

---

## Tier 5 — Operator-grade docs (complete)

| # | Task | Status | Files | Tests | Validation | Result |
|---|---|---|---|---|---|---|
| 17 | `docs/GIS_EXPORT_GUIDE.md` | ✅ complete | `docs/GIS_EXPORT_GUIDE.md` | doc-only | manual review | QGIS + Google Earth import + KML deferral note |
| 18 | `docs/NEXT_100_TASKS.md` | ✅ complete | `docs/NEXT_100_TASKS.md` | doc-only | manual review | 45 tasks across 6 tiers, ~94 h estimated |
| 19 | `docs/RELEASE_READINESS.md` | ✅ complete | `docs/RELEASE_READINESS.md` | doc-only | manual review | Runbook: stages + modes + report shape + common failures + verification matrix |
| 20 | `docs/ROI_TASK_LEDGER.md` | ✅ complete | this file | doc-only | manual review | The scorecard you're reading |

---

## Tier 6 — Tests added (partial)

| # | Task | Status | Files | Tests | Validation | Result |
|---|---|---|---|---|---|---|
| 21 | `tests/test_release_check.py` | ⬜ not started | (planned) | (this test) | (planned) | D2 |
| 22 | `tests/test_run_modes.py` | ⬜ not started | (planned) | (this test) | (planned) | D2 |
| 23 | `tests/test_provenance_utils.py` | ⬜ not started | (planned) | (this test) | (planned) | D2 |
| 24 | `test_schema_validation.py` extension | ✅ complete | `tests/test_schema_validation.py` | 4 new tests (index lookups, schema_file resolution, dedup) | 22 passed | — |
| 25 | `test_pr_intel_adapter.py` extension | ✅ complete | `tests/test_pr_intel_adapter.py` (via existing) | 16 passed | byte-identical export verified separately | — |
| 26 | `test_spiderweb_intake.py` extension | ⬜ not started (depends on Tier 3 #13) | — | — | — | Will land with Tier 3 #13 |
| 27 | `test_screenshot_inventory.py` extension | 🚧 blocked | (depends on Tier 4 #16) | — | — | — |

---

## Workstream B (RLSM extraction) — production-ready, with NEXT-100 follow-ups

| # | Task | Status | Files | Tests | Validation | Result |
|---|---|---|---|---|---|---|
| B1 | Finish bulk OCR | ✅ complete | (Mac run) | `tests/test_rlsm_pipeline.py` | `ocr_status='ok'` = 11,924 | 99.98% OCR coverage (2 un-OCR-able files: 1 corrupt + 1 unreadable) |
| B2 | Unlabeled vision pass | ✅ complete | (Mac run after lock fix) | `tests/test_rlsm_pipeline.py` | `unlabeled_poi_candidates` covers 11,857 / 11,924 (99.4%) | 526,918 candidates |
| B3 | Derived extractors | ✅ complete | `fr24/rlsm_extractors.py` | `tests/test_rlsm_pipeline.py` | 9,765 aircraft / 11,876 labeled / 39,580 review-queue | — |
| B4 | Export + coverage | ✅ complete | `fr24/rlsm_export.py`, `fr24/rlsm_coverage.py` | `tests/test_rlsm_pipeline.py::test_exports_reproducible` | 14 artifacts deterministic | — |
| B5 | Invariant tests | ✅ complete | `tests/test_rlsm_pipeline.py` | 10/10 passed | — | — |
| B6 | Track schema.sql + HANDOFF.md | ✅ complete | `.gitignore`, `data/rlsm/schema.sql`, `data/rlsm/HANDOFF.md` | manual | `git ls-files data/rlsm/` shows both | Commit `e5d0928` |
| B7 | Harden `test_exports_reproducible` | ⬜ not started | `tests/test_rlsm_pipeline.py` | (this test) | — | NEXT_100 #N6 |
| B8 | Commit RLSM code | ✅ complete | (squash-merge #56) | — | — | Commit `5e3832...` |
| B-lock | rlsm_unlabeled DB lock | ✅ complete | `fr24/rlsm_unlabeled.py`, `fr24/rlsm_extractors.py`, `fr24/rlsm_ocr.py` | `tests/test_rlsm_pipeline.py` 10/10 | `--limit 20` runs cleanly | `timeout=30.0` + `PRAGMA busy_timeout=30000` |
| B-zone | `map_center→label_layer` zone fix | ✅ complete | `fr24/rlsm_unlabeled.py:161` | functional verification on 3 images | candidates emit (54/23/60) instead of KeyError | — |
| B-recovered-test | `identity_status='recovered'` test fix | ✅ complete | `tests/test_rlsm_pipeline.py`, `data/rlsm/schema.sql` | `tests/test_rlsm_pipeline.py` 10/10 | — | Commit `96fb31f` |

---

## Status summary

| Tier | Complete | Partial | Blocked | Not started |
|---|---|---|---|---|
| Tier 1 | 10 / 10 | 0 | 0 | 0 |
| Tier 2 | 2 / 2 | 0 | 0 | 0 |
| Tier 3 | 1 / 2 | 0 | 0 | 1 |
| Tier 4 | 2 / 2 (superseded by RLSM) | 0 | 0 | 0 |
| Tier 5 | 4 / 4 | 0 | 0 | 0 |
| Tier 6 | 3 / 7 | 0 | 1 | 3 |
| Workstream B | 9 / 11 | 0 | 0 | 2 |
| **Total** | **29 / 38** | **0** | **2** | **7** |

**Headline:** Tier 1 + Tier 2 + Tier 4 (superseded by RLSM) + Tier 5 are **100% complete**. Tier 3 fields landed in PR #63; MBIL-X landed in PR #64. Tier 6 partially in flight. Workstream B operational at 99.4% coverage.

---

## Cross-references

- [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md) — backlog for everything not in this ledger.
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md) — the gate this work is gated against.
- [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md), [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md), [`GIS_EXPORT_GUIDE.md`](GIS_EXPORT_GUIDE.md) — referenced from individual rows.
