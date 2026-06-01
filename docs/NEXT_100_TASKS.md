# Next 100 Tasks

Backlog of release-readiness work beyond the Tier 1–Tier 5 sweep documented in the [main plan](../%2E%2E/%2E%2E/.claude/plans/you-are-claude-code-tingly-salamander.md) and the [ROI Task Ledger](ROI_TASK_LEDGER.md).

Tasks are grouped by impact tier. Within each tier, the **one-line scope** + **estimated effort** + **dependency blockers** are listed so an operator can pick up any item independently.

Effort is per-engineer-hour and assumes the existing test scaffolding is reused. Estimates carry ±50% uncertainty.

---

## High-impact follow-ups (immediate next sweep)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **N1** | JSON Schema for `release_report.json` | Define `schemas/release_report.schema.json`; register in `schema_index.json`. | 1 h | None |
| **N2** | JSON Schema for `integration_report.json` | Define `schemas/integration_report.schema.json`; register in `schema_index.json`; add validation in `release_check.export_pr_intel`. | 1 h | None |
| **N3** | JSON Schemas for the 14 RLSM CSV outputs | One schema per artifact; register all in `schema_index.json`. | 3 h | None |
| **N4** | Canonicalize the recover-tails-by-rawtext script | Move the un-tracked rescue logic into `scripts/rlsm_recover_tails_by_rawtext.py`; emit `processing_runs` row with `run_kind='recover_tails'`. | 2 h | Already done in D3 (this sweep) |
| **N5** | Add `--workers` parallelism to `rlsm_unlabeled` | Mirror `rlsm_ocr_parallel`'s `ProcessPoolExecutor` pattern. Cuts a full backfill from ~70 min single-thread to ~18 min on 4 workers. | 2 h | None (busy_timeout fix already landed) |
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

## Tier 4 follow-ups (FR24 hardening)

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **T4-31** | Rich resumability for `fr24/batch_run.py` | Per-file ledger entries with `attempted_at`/`succeeded_at`/`failed_at`/`error_class`. | 4 h | T4-DECISION (active runner) |
| **T4-32** | Per-image OCR failure log | Structured `fr24_ocr_failures.jsonl` (path, sha256, zone, error). | 2 h | None |
| **T4-33** | FR24 batch manifest with reproducibility | Inject D3 block into the FR24 batch output. | 1 h | T4-DECISION |
| **T4-34** | FR24 summary Markdown | One-page operator summary per batch (counts, top errors, ETA). | 2 h | None |
| **T4-35** | Align `screenshot_inventory.py` enum with RLSM's | Use `ingest_status` + `ocr_status` vocabularies; avoid inventing a third. | 2 h | None |
| **T4-36** | FR24 batch dry-run | `--dry-run` prints planned actions, writes nothing. | 1 h | T4-DECISION |
| **T4-37** | FR24 batch offset | `--offset N` skips first N rows (complements existing `--limit`). | 30 m | T4-DECISION |
| **T4-38** | RLSM `--workers` (see N5) | Listed here too for completeness. | 2 h | None |
| **T4-39** | FR24 batch resume from a specific ledger row | `--resume-from <sha256>` to retry a specific failure. | 1 h | T4-DECISION + T4-31 |
| **T4-40** | OCR engine pinning per zone | `ZONE_OCR_CONFIG` keys → engine version; record in `processing_runs.notes`. | 2 h | None |

**T4-DECISION** (referenced above): determine whether `fr24/batch_run.py` is still the active path or has been superseded by RLSM's `fr24.rlsm_ocr_parallel`. The 16-script analysis suite (commit `39918c9`) suggests RLSM is the primary path; if confirmed, Tier 4 patches retarget the RLSM runner.

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
| **B-flight-track** | `flight_track_features` extractor | Detect path shapes (linear/curve/loop/orbit/hover) from track points + heading. Populate the currently-empty table. | 8 h | None |
| **B-geo-anchors** | `geo_anchors` pixel→lat/lon | Build a per-screenshot homography from known label positions; populate `geo_anchors`. | 12 h | None |
| **B-integrate** | Fold RLSM into `run_all.py` / Makefile / CI | Add `--rlsm-status` flag to `run_all.py`; add `tests/test_rlsm_pipeline.py` to the default suite (it auto-skips on missing DB). | 3 h | None |
| **B-dedup-unique** | UNIQUE constraint on `aircraft_observations` | Add `(screenshot_id, registration, source_zone)` unique index to prevent run-65/run-67 type duplicates. | 1 h | Migration |

---

## Cross-workstream

| # | Task | Scope | Effort | Blockers |
|---|---|---|---|---|
| **X1** | Pre-commit hook | Run `python -m py_compile`, `pytest tests/test_schema_validation.py`, `release_check --skip-tests --demo`. | 2 h | None |
| **X2** | CI smoke for release gate | Add a `release-check` job to `.github/workflows/ci.yml` matching the local Makefile target. | 1 h | None |
| **X3** | Document iOS-friendly single-line commands | Audit `EXECUTION_GUIDE.md` (if present) for line-continuation-free recipes for a-Shell users. | 2 h | None |

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
