# Next 100 Tasks

> **Prior sweep.** This is the first optimization sweep (Tier 1–5 + Workstream B +
> Cross-workstream, mostly complete). The current roadmap is
> [`NEXT_100_TASKS_V2.md`](NEXT_100_TASKS_V2.md), which carries the still-open
> items below forward. New work should be tracked there.

> **Boundary supersession (2026-08-26).** Every FR24/RLSM/OCR item in this
> historical sweep is `SUPERSEDED` for Spiderweb. Executable ownership moved to
> `skywatcher-pr`; these rows are traceability only and must not be implemented
> in this repository. Spiderweb retains only the producer-neutral homography
> utilities documented in [`FR24_EXECUTABLE_RETIREMENT.md`](FR24_EXECUTABLE_RETIREMENT.md).

Backlog of release-readiness work beyond the Tier 1–Tier 5 sweep documented in the [main plan](../%2E%2E/%2E%2E/.claude/plans/you-are-claude-code-tingly-salamander.md) and the [ROI Task Ledger](ROI_TASK_LEDGER.md).

Tasks are grouped by impact tier. Within each tier, the **one-line scope** + **estimated effort** + **dependency blockers** are listed so an operator can pick up any item independently.

Effort is per-engineer-hour and assumes the existing test scaffolding is reused. Estimates carry ±50% uncertainty.

---

## High-impact follow-ups (immediate next sweep)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **N1** | JSON Schema for `release_report.json` | Define `schemas/release_report.schema.json`; register in `schema_index.json`. | 1 h | None |
| **N2** | JSON Schema for `integration_report.json` | Define `schemas/integration_report.schema.json`; register in `schema_index.json`; add validation in `release_check.export_pr_intel`. | 1 h | None |
| **N3** | RLSM CSV schemas — **SUPERSEDED** | Historical schema work; any current RLSM contract belongs in `skywatcher-pr`. | — | Transferred |
| **N4** | Recover-tails runner — **SUPERSEDED** | Historical implementation; executable ownership moved to `skywatcher-pr`. | — | Transferred |
| **N5** | RLSM worker parallelism — **SUPERSEDED** | Historical implementation from #129; the Spiderweb runner was removed at boundary closure. | — | Transferred |
| **N6** | Harden `test_exports_reproducible` | Change from "on-disk vs fresh export" to "two fresh exports" — decouples from stale-artifact tripwire. | 30 m | None |

---

## Tier 2 follow-ups (validation contracts)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **T2-18** | Geometry validity checks via shapely | Add `validate_geometry(features)` to `SchemaValidator`; enforce on GeoJSON exports. | 3 h | shapely dependency review |
| **T2-19** | Full null-field policy enforcement | Reject `null` for required cols at validation time; route to enriched review queue with `error_type='null_field'`. | 2 h | None |
| **T2-20** | Confidence-scale enforcement tests | Test that every `confidence` column is in `[0,1]` and labeled HIGH/MEDIUM/LOW/REJECTED per [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md#confidence-scale-policy). | 2 h | None |

---

## Tier 3 follow-ups (Spiderweb language)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **T3-21** | Add `fact_status` to spiderweb_intake | `observed` if confidence ≥ T1 + ≥2 corroborating; else `inferred`. | 1 h | None |
| **T3-22** | Add `spiderweb_role` field | Derived: POI→`node`, ILAP→`path`, corridor→`edge`, aasb_edge→`airport_link`. | 30 m | None |
| **T3-23** | Add `access_assertion_level` field | `public_record` if airport-anchored; else `derived_observation`. | 30 m | None |
| **T3-24** | Add `nearest_municipal_boundary_m` field | `round(min_dist_deg * 111000, 1)`. | 30 m | None |
| **T3-25** | **MBIL-X decision** | Decide semantics of MBIL-X (unknown / unclassified / off-island). Spec, then implement. | 2 h + decision time | **Decision-needed flag** — see [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md). |
| **T3-26** | Full MBIL field expansion in POI/corridor records | Currently MBIL scoring fires on spiderweb candidates only; extend to native POI + corridor records in the producer. | 3 h | T3-25 (if MBIL-X used) |
| **T3-27** | MBIL-only guardrail test | Test confirms `_assign_evidence_tier` caps MBIL-only candidates at T4. | 1 h | None |
| **T3-28** | `aasb_mbil_corridor_flag` per AASB edge | Add a per-edge flag in `aasb_airspace_edges.csv` indicating MBIL-2+ on both endpoints. | 1 h | T3-26 |
| **T3-29** | Add `aasb_mbil_corridor_flag` to spiderweb_overlay | Carry the AASB-level flag into the spiderweb observations layer. | 30 m | T3-28 |
| **T3-30** | Spiderweb terrain DEM hook | Stub interface for terrain elevation lookups; document API. | 4 h | DEM/terrain source decision |

---

## Tier 4 follow-ups (FR24 hardening) — **SUPERSEDED / TRANSFERRED**

**Historical decision (DG-2): RLSM was canonical for the old in-repo airspace
surface.** That decision is now superseded by the repository boundary: FR24/RLSM
ingestion and OCR belong to `skywatcher-pr`, and the Spiderweb executables were
removed. No row in this section authorizes rebuilding them here.

The original T4-31..T4-40 list is preserved below for traceability, but each item is **marked with its replacement** in RLSM. Items already implemented on the RLSM side carry ✅; items genuinely deferred are flagged.

| # | Original task (fr24/batch_run.py) | RLSM replacement | Status |
|---|---|---|---|
| **T4-31** | Per-file ledger with `attempted_at`/`succeeded_at`/`failed_at`/`error_class` | `processing_runs` table records every `run_kind` invocation with `started_at`/`ended_at`/`status`/`n_processed`/`n_failed`/`notes` (per-tail breakdowns in `notes` for `recover_tails`) | ✅ implemented in RLSM |
| **T4-32** | `fr24_ocr_failures.jsonl` (path, sha256, zone, error) | `ocr_observations.ocr_status='failed'` + `.ocr_error`; queryable via `SELECT * FROM ocr_observations WHERE ocr_status='failed'` | ✅ schema in place; consider exporting a derived JSONL if operators need a flat file |
| **T4-33** | D3 reproducibility block on FR24 batch output | `processing_runs.git_sha` + per-export reproducibility block on the 14 RLSM CSVs/JSONL (PR #59 added the schema_index, PR #61 added the schemas) | ✅ implemented |
| **T4-34** | One-page operator summary per batch | `outputs/rlsm_coverage_report.md` is the canonical summary; `rlsm_coverage.py` regenerates it on demand | ✅ implemented |
| **T4-35** | Align `screenshot_inventory.py` enum with RLSM's | `screenshots.ingest_status` (`ok`/`corrupt`/`unreadable`) + `.ocr_status` (`pending`/`ok`/`partial`/`failed`) ARE the canonical RLSM vocabulary. `fr24/screenshot_inventory.py` retains its CSV format for backward-compat; new producers should write to the SQLite directly. | ✅ vocabulary defined; legacy CSV path tolerated |
| **T4-36** | `--dry-run` on the batch runner | `scripts/rlsm_recover_tails_by_rawtext.py --dry-run` already exists; `fr24/rlsm_unlabeled` and `rlsm_ocr_parallel` accept `--limit` for sampling | ✅ pattern established; can be propagated to other runners if needed |
| **T4-37** | `--offset N` to skip first N rows | Replaced by SQL-driven targeting: every RLSM runner queries `WHERE ocr_status='pending'` (or similar) + `ORDER BY screenshot_id` so resumption is implicit. `--limit N` complements. | ✅ implicit via SQL |
| **T4-38** | RLSM `--workers` parallelism | `fr24/rlsm_ocr_parallel` (multi-worker since day 1) + `fr24/rlsm_unlabeled --workers N` (added in PR #60) | ✅ implemented |
| **T4-39** | `--resume-from <sha256>` | RLSM runners are resumable via the `NOT EXISTS`-style WHERE clauses — restart picks up where it left off. Per-sha256 retry is achievable by manually flipping `ocr_status='pending'` for a row. | ✅ via SQL |
| **T4-40** | OCR engine pinning per zone (`ZONE_OCR_CONFIG` → engine version) | `ocr_observations.engine` + `.engine_version` + `.psm` columns ARE pinned per row. Operators can audit drift via `SELECT DISTINCT engine, engine_version, psm FROM ocr_observations`. | ✅ implemented |

**Action items going forward** — none in Spiderweb. Any live RLSM/OCR gap must
be tracked and implemented in `skywatcher-pr`; references here are historical
evidence only.

---

## Tier 5 follow-ups (GIS / docs)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **T5-41** | Standardized GeoJSON property bag | Define a common `_meta` sub-object on every Feature carrying `source_artifact`, `produced_at`, `producer_module`. | 2 h | None |
| **T5-42** | KML export | `_export_kml` in `integration/pr_intel_adapter.py` using `simplekml` (optional dep). | 2 h | `simplekml` install |
| **T5-43** | Full corridor decomposition with canonical names | Map `recurrence_score`/`loiter_score`/`infra_alignment_score`/`overall_confidence` to operator-facing labels. | 3 h | None |
| **T5-44** | Municipal-centroid input hook | Allow operators to supply a custom centroid CSV instead of the hardcoded 72-municipality list. | 2 h | None |
| **T5-45** | DEM/terrain placeholder interface | Same as T3-30; deferred to NEXT_100. | 4 h | DEM source |
| **T5-46** | QGIS style XML pack | Ship `.qml` style files for the GeoJSON outputs (referenced by [`GIS_EXPORT_GUIDE.md`](GIS_EXPORT_GUIDE.md)). | 2 h | None |
| **T5-47** | Auto-generate map preview PNGs | Headless `matplotlib` / `contextily` pre-rendered map for each GeoJSON export. | 3 h | None |
| **T5-48** | Operator quick-start runbook | A 1-page "getting started" doc above the existing operator-grade docs. | 1 h | None |
| **T5-49** | KML export — pipeline-native | If T5-42 is wired in, deprecate the `ogr2ogr` workaround in [`GIS_EXPORT_GUIDE.md`](GIS_EXPORT_GUIDE.md). | 30 m | T5-42 |

---

## Workstream B follow-ups (RLSM)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **B-flight-track** | **Superseded by repository boundary** | Historical pixel-track work transferred to `skywatcher-pr`. | — | Transferred |
| **B-geo-anchors** | **Partially retained / otherwise superseded** | Generic evidence-bounded homography remains; screenshot/OCR anchor derivation belongs to `skywatcher-pr`. | — | Transferred |
| **B-integrate** | **Superseded by repository boundary** | RLSM execution and status belong to `skywatcher-pr`; Spiderweb's retired flag must not be restored. | — | Closed |
| **B-dedup-unique** | **Superseded by repository boundary** | Historical airspace-persistence hardening transferred to `skywatcher-pr`. | — | Transferred |

---

## Cross-workstream

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **X1** | ✅ Pre-commit hook shipped (PR #69) — `.pre-commit-config.yaml` runs py_compile + schema-validation pytest + release_check demo on matching file changes. | — | done |
| **X2** | ✅ CI release-check job shipped (PR #69) — `.github/workflows/ci.yml` now has a `release-check` job that runs `release_check.py --skip-tests --demo` after the main test job, with structural-validity asserts on the report. | — | done |
| **X3** | ✅ iOS-friendly EXECUTION_GUIDE.md shipped (PR #69) — 2 backslash-continuation blocks rewritten as single-line iOS / a-Shell commands; 0 remaining `\` line continuations. | — | done |

---

## Effort summary

| Tier | Open tasks | Total estimate |
|---|---|---|
| High-impact | 6 | ~10 h |
| Tier 2 | 3 | ~7 h |
| Tier 3 | 10 | ~14 h + 1 decision |
| Tier 4 | 10 | ~17 h + 1 decision (T4-DECISION) |
| Tier 5 | 9 | ~17 h |
| Workstream B | 4 | ~24 h |
| Cross-workstream | 3 | ~5 h |
| **Total** | **45** | **~94 h** |

---

## Cross-references

- [`ROI_TASK_LEDGER.md`](ROI_TASK_LEDGER.md) — running scorecard with statuses + files touched per task.
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md) — the gate these tasks are gated against.
- [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) — current artifact contracts.
- [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md) — vocabulary the Tier 3 tasks extend.
