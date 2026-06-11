# Schema & Export Contracts

**Purpose.** One place to look up what every release-pipeline output artifact is, what its schema is, what its provenance fields are, and how its rows are deduplicated. This document is the human-readable rendering of [`schemas/schema_index.json`](../schemas/schema_index.json) — the machine-readable source of truth.

**Who consumes this.** Operators planning a release, downstream integrators pointing at our artifacts, and anyone adding a new output to the pipeline.

**How to use it.** Find your artifact in the workstream tables below. The columns tell you:
- **Schema** — which JSON Schema validates this artifact (or `—` for reports/manifests with no schema yet).
- **Format / CRS** — file format; coordinate reference system for spatial outputs.
- **Required cols** — top columns the schema mandates (see the schema file for the full list).
- **Provenance** — fields that tie each row back to its source.
- **Dedup key** — the natural key for deduplication.

Programmatically: `SchemaValidator().index_lookup("airspace_events.parquet")` returns the full index entry for any artifact, or `None` if it isn't registered. `SchemaValidator().index_artifacts()` returns the full list.

---

## Workstream: PR Intel (`integration/pr_intel_adapter.py`)

The PR Intel adapter emits 8 data artifacts + 2 reports per export.

| Artifact | Schema | Format / CRS | Required cols (summary) | Provenance | Dedup key |
|---|---|---|---|---|---|
| `airspace_events.parquet` | `flight_event` | parquet | flight_id, callsign, takeoff_time, landing_time, origin_airport, destination_airport | screenshot_id, source_path, sha256, ocr_confidence, coordinate_method, coordinate_confidence, review_status | `flight_id` |
| `aircraft_profiles.parquet` | `aircraft_profile` | parquet | callsign, aircraft_type, operator, primary_mission, confidence_level | screenshot_id, source_path, sha256, ocr_confidence, review_status | `callsign` |
| `track_points.parquet` | `track_point` | parquet | id, flight_id, timestamp, latitude, longitude | screenshot_id, source_path, sha256, coordinate_method, coordinate_confidence | `id` |
| `screenshot_evidence.parquet` | `screenshot` | parquet | screenshot_id, image_path, processed_at, ocr_confidence | sha256, coordinate_method, coordinate_confidence, estimated_error_m, review_status | `screenshot_id` |
| `mission_inferences.parquet` | `mission_inference` | parquet | flight_id, mission_type, total_score, confidence_level, scored_at | screenshot_id, source_path, sha256, review_status | `flight_id` |
| `anomaly_index.parquet` | `anomaly` | parquet | alert_id, flight_id, category, severity, timestamp | screenshot_id, source_path, sha256, review_status | `alert_id` |
| `gis_airspace_features.geojson` | `gis_feature` | geojson / EPSG:4326 | feature_id, name, type | screenshot_id, sha256, source_path | `feature_id` |
| `route_lines.geojson` | `gis_feature` | geojson / EPSG:4326 | flight_id, callsign, duration_min | screenshot_id, sha256, source_path | `flight_id` |
| `source_manifest.json` | `export_manifest` | json | generated_at, db_path, files, **reproducibility** | reproducibility block (D3) | — |
| `integration_report.json` | — *(no schema yet)* | json | generated_at, overall_status, gates | — | — |

**Determinism (D4).** All six parquet exporters sort rows before writing (`airspace_events` by `flight_id`, `aircraft_profiles` by `callsign`, `track_points` by `(flight_id, timestamp, id)`, `screenshot_evidence` by `screenshot_id`, `mission_inferences` by `flight_id`, `anomaly_index` by `alert_id`). Two consecutive exports against an unchanging DB produce byte-identical output.

**GeoJSON provenance (D6).** Both `gis_airspace_features.geojson` and `route_lines.geojson` carry per-feature `screenshot_id` / `sha256` / `source_path` from the linked first screenshot. `source_manifest.json` carries `geo_summary` (bbox / centroid / feature_count / geometry_types) for each GeoJSON.

---

## Workstream: Spiderweb bridges (`integration/aasb_airspace_bridge.py`, `integration/ilap_airspace_bridge.py`, `readiness/spiderweb_intake.py`)

| Artifact | Schema | Format / CRS | Required cols (summary) | Provenance | Dedup key |
|---|---|---|---|---|---|
| `spiderweb_overlay_candidates.geojson` | `spiderweb_observation` | geojson / EPSG:4326 | source_layer, candidate_type, lat, lon, confidence, evidence_tier | linked_flight_id, linked_aircraft, corridor_id | — |
| `spiderweb_gap_audit.json` | — | json | gaps, **reproducibility** | reproducibility | — |
| `spiderweb_ingest_manifest.json` | `spiderweb_intake_manifest` | json | generated_at, db_path, files | reproducibility | — |
| `aasb_airspace_edges.csv` | `aasb_export` | csv / EPSG:4326 | edge_id, from_node, to_node, from/to_lat/lon, weight, confidence_score | dominant_callsign | `edge_id` |
| `airspace_poi_candidates.geojson` | `spiderweb_observation` | geojson / EPSG:4326 | candidate_type, confidence | source_zone, raw_excerpt | — |
| `airspace_ilap_candidates.geojson` | `ilap_corridor_candidate` | geojson / EPSG:4326 | candidate_type, recurrence_score, loiter_score, infra_alignment_score, overall_confidence | — | — |
| `airspace_corridor_candidates.geojson` | `ilap_corridor_candidate` | geojson / EPSG:4326 | candidate_type, overall_confidence | — | — |

The overlay carries a top-level `summary` block (bbox / centroid / feature_count / geometry_types) added by `SpiderwebIntake._write_outputs()` via `provenance_utils.feature_collection_summary()`.

---

## Workstream: RLSM extraction (`fr24/rlsm_*`, `scripts/rlsm_*`) — migrated

> **Migrated.** The RLSM extraction pipeline (`fr24/rlsm_*`, `scripts/rlsm_*`,
> `data/rlsm/schema.sql`, `tests/test_rlsm_pipeline.py`) moved to
> [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr) in 2026-06 (PRs
> #110/#111). The contract below is retained for historical reference; these
> artifacts are no longer produced by this repo.

The RLSM pipeline emits 14 derived artifacts under `outputs/` plus a markdown coverage report. None has a JSON Schema registered yet (Tier 2 follow-up; see [`docs/NEXT_100_TASKS.md`](NEXT_100_TASKS.md) when it lands).

| Artifact | Format | Required cols (summary) | Provenance | Dedup key |
|---|---|---|---|---|
| `outputs/rlsm_ingest_manifest.csv` | csv | screenshot_id, sha256, filename, rel_path, month_bucket, ingest_status, ocr_status | sha256, ingested_at | `sha256` |
| `outputs/rlsm_duplicate_report.csv` | csv | dup_group_id, group_size, sha256, filename, rel_path | sha256 | `dup_group_id` |
| `outputs/rlsm_failed_files.csv` | csv | screenshot_id, filename, rel_path, ingest_status, ingest_error | — | `screenshot_id` |
| `outputs/ocr_raw_by_zone.jsonl` | jsonl | screenshot_id, zone, raw_text, confidence_mean | run_id, engine, psm, observed_at | — *(append-only)* |
| `outputs/ocr_normalized_labels.csv` | csv | poi_id, screenshot_id, raw_label, normalized_label, poi_type_guess, confidence | filename, observed_at, review_status | `poi_id` |
| `outputs/labeled_pois.csv` | csv | poi_id, screenshot_id, raw_label, normalized_label, bbox, centroid, poi_type_guess, confidence | filename, observed_at, review_status | `poi_id` |
| `outputs/unlabeled_poi_candidates.csv` | csv | candidate_id, screenshot_id, candidate_type, bbox, centroid, confidence | filename, evidence_features, observed_at, review_status | `candidate_id` |
| `outputs/aircraft_observations.csv` | csv | aircraft_obs_id, screenshot_id, registration, callsign, aircraft_type, altitude_ft, speed_kt, heading_deg, identity_status, confidence | filename, filename_ts, source_zone, raw_excerpt, observed_at | `aircraft_obs_id` |
| `outputs/flight_track_features.csv` | csv | track_feat_id, screenshot_id, path_shape, has_loop, has_orbit, has_hover, confidence | filename, observed_at | `track_feat_id` |
| `outputs/manual_review_*.csv` (×5) | csv | review_id, screenshot_id, item_kind, reason, severity, review_status | filename, item_ref_table, item_ref_id, created_at | `review_id` |
| `outputs/rlsm_coverage_report.md` | markdown | — | — | — |

**RLSM-specific note — `aircraft_observations.identity_status`** has **five** valid values:
- `confirmed` — registration extracted directly from `aircraft_card` zone OCR (primary path).
- `partial` — extractor found partial identity (callsign or type only).
- `conflicting` — multiple competing OCR signals for the same observation.
- `unknown` — no extractor signal at all.
- `recovered` — registration discovered by a separate raw-text rescue pass that scans `ocr_observations.raw_text` for known FAA tail numbers (see [`schema.sql`](../data/rlsm/schema.sql) inline comment and `tests/test_rlsm_pipeline.py::test_aircraft_observations_well_formed`).

`flight_track_features` and `geo_anchors` tables are **deferred** — schema is ready but no extractor yet (Workstream B follow-up).

---

## Workstream: PRII readiness + Release gate

| Artifact | Schema | Format | Required cols (summary) | Provenance | Dedup key |
|---|---|---|---|---|---|
| `prii_readiness_report.json` | `prii_readiness_report` | json | generated_at, export_dir, readiness_status, blockers, warnings, missing_inputs, gate_summary | `release` (link to release_report when present) | — |
| `release_report.json` | — *(no schema yet)* | json | metadata, syntax_check, core_tests, validate, export_pr_intel, export_spiderweb, earthgpt_selftest, overall_status, failure_reasons | `metadata.reproducibility` (8-key block per D3) | — |

`release_report.json` is the umbrella artifact (D1). It references `integration_report.json` (via `export_pr_intel.integration_report`) and `prii_readiness_report.json` (via the readiness engine's `release` link, non-breaking).

---

## Reproducibility block (D3)

Every manifest carries a `reproducibility` block with these 8 keys (built by [`provenance_utils.reproducibility_metadata()`](../provenance_utils.py)):

| Key | Meaning |
|---|---|
| `timestamp_utc` | ISO-8601 timestamp of the export |
| `repo_commit` | `git rev-parse HEAD` (or `"unknown"` outside a git repo) |
| `python_version` | `platform.python_version()` |
| `platform` | `<system>-<release>-<machine>` |
| `command` | The operator-visible invocation (defaults to `sys.argv`) |
| `input_paths` | Paths the operator declared as inputs |
| `input_sha256s` | SHA-256 of each input path (`"skipped_large_file"` over 32 MB; `"unknown"` if unreadable) |
| `mode` | `"normal"` / `"strict"` / `"demo"` |

Carried by: `release_report.json` (`metadata.reproducibility`), `source_manifest.json` (PR Intel), `spiderweb_ingest_manifest.json` (AASB), `spiderweb_gap_audit.json` (intake).

---

## Null-field policy

Different "missing" semantics are recorded distinctly rather than collapsed to one sentinel:

| Sentinel | Meaning | When to use |
|---|---|---|
| `null` (JSON) / `None` (Python) | Field truly has no value | Type-correct absence; never confused with "unknown" |
| `"unknown"` (string) | Producer attempted to extract and failed | OCR/CV ran and got nothing usable |
| `"not_applicable"` | Field is structurally irrelevant for this row's type | E.g., `corridor_id` on a POI candidate |
| `"not_extracted"` | Field is in the schema but not yet extracted by the current pipeline version | Distinguishes "we never tried" from "we tried and failed" |

The schema index records `fact_status_default` per artifact as a coarse summary:
- `observed` — primary-extractor outputs from direct measurement (parquet exports, inventory).
- `inferred` — derived/scored outputs (mission inferences, anomalies, ILAP candidates).
- `null` — reports and manifests (no per-row factual stance).

---

## Confidence-scale policy

All `confidence` / `*_confidence` fields are in the closed interval **[0.0, 1.0]**:

| Label | Range | Operator action |
|---|---|---|
| `HIGH` | `≥ 0.70` | Trust without manual review |
| `MEDIUM` | `0.40 – 0.70` | Spot-check before downstream propagation |
| `LOW` | `< 0.40` | Route to manual review queue |
| `REJECTED` | `< 0.25` | Drop entirely (do not export) |

These thresholds are the **canonical** scale used by the PRII readiness engine, the ILAP corridor scorer, and the RLSM aircraft extractor. Re-using them in any new producer keeps the operator vocabulary consistent.

---

## Adding a new artifact

1. **Write the JSON Schema** under `schemas/<name>.schema.json` (or reuse an existing one).
2. **Add an entry** to `schemas/schema_index.json` with `workstream`, `artifact_path`, `schema_name`, `schema_file`, `format`, `crs`, `required_columns_summary`, `provenance_fields`, `dedup_key`, `fact_status_default`.
3. **Update this doc** — append a row to the relevant workstream table.
4. **Test:** `pytest tests/test_schema_validation.py` — the existing `test_index_schema_files_resolve_on_disk` will fail-loud if you reference a missing file.
