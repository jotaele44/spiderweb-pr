# SpiderWeb FR24 Removal Ledger

**Date:** 2026-07-20. FR24 screenshot-processing capability moved to skywatcher-pr.

## Removed (git rm)
| Path | What | Reason |
|---|---|---|
| `pipeline/flight_analyzer.py` | `FlightRadarOCR`, `FlightAnalyzer`, `FlightDatabase`, `CoordinateMapper`, `FlightGrouper`, `process_all_images`, `link_screenshots_to_flights`, `/mnt/user-data/uploads` | Core FR24 screenshot OCR + reconstruction + DB ownership → Skywatcher |
| `pipeline/geo_anchors.py` | `GeoAnchor`, OCR-label anchor matching, screenshot-pixel homography | Current-main FR24 screenshot georeferencing residue → Skywatcher |
| `pipeline/hardened_pipeline.py` | `HardenedFlightAnalyzer`, `process_with_hardening` | FR24 screenshot orchestrator (also already broken: imported the deleted `pipeline/ensemble_ocr.py`) |
| `scripts/ocr_full.py` | full OCR batch runner | FR24 screenshot batch processing |
| `scripts/ocr_parallel.py` | parallel OCR runner | FR24 screenshot batch processing |
| `scripts/ocr_checkpoint.py` | checkpointed OCR runner | FR24 screenshot batch processing |
| `tests/test_performance.py` | exercised `FlightDatabase._init_tables` | FR24-only test (screenshot DB) |
| `tests/test_geo_anchors.py` | tested screenshot-pixel homography through the removed analyzer stack | FR24-only test |

## Edited
| Path | Change |
|---|---|
| `run_all.py` | Removed `run_phase_0`, `run_phase_1`, `run_home_base`, `run_fleet_correlation`, `_run_export_home_base`, `print_rlsm_status`; removed flags `--image-dir`, `--images`, `--phase 0/1`, `--home-base`, `--fleet-correlation`, `--export-home-base`, `--rlsm-status`; `--phase` now `{2,3,4}`. **Added** `--ingest-skywatcher PATH` + `run_ingest_skywatcher()`. Banner/help updated. |
| `server/backend/main.py` | Removed `--images` wiring from `PipelineRunRequest` / `/pipeline/run`. |
| `pyproject.toml` | `airspace` extra: removed screenshot-only libs `opencv-python`, `pytesseract`, `pillow-heif`, `Pillow` (kept `jsonschema`, `pyarrow`, `PyYAML`). |
| `.gitignore` | Added `*.db-wal/-shm`, `skywatcher.db`, `inputs/screenshots/`, bridge-ingest runtime dir. |

## Retained deliberately (KEEP, with rationale)
| Path | Why kept |
|---|---|
| `pipeline/hardening_layer.py` | `TemporalValidator` is consumed by the retained `integration/pr_intel_adapter.py`; pure validation logic, no screenshot/OCR code. `tests/test_temporal_validator.py` still passes. |
| `docs/legacy/scripts/rlsm_unlabeled.py`, `docs/legacy/tests/test_rlsm_unlabeled.py` | Historical snapshot retained outside active/package paths by current `main`; excluded from the zero-active-code claim. |
| `pipeline/{aircraft_intelligence,gis_intelligence,mission_inference,operational_intelligence}.py` | Downstream intelligence consuming `flights`/`track_points`; not screenshot processing. Now fed by the bridge. |
| `integration/*` (pr_intel_adapter, ilap/aasb bridges, schema_validation, kml_export, mbil) | Downstream / export bridges; not screenshot processing. |
| FR24 record schemas (`screenshot.schema.json`, `ocr_raw_by_zone`, `ocr_normalized_labels`, `extracted_field`, `aircraft_observations`, `flight_track_features`) | Retained as **inert data contracts**. Physical deletion cascades into `schemas/schema_index.json` + `tests/test_schema_validation.py` + CI; `schema_validation` skips absent tables gracefully. Recommended follow-up cleanup PR. |

## Added (retained bridge)
| Path | What |
|---|---|
| `integration/skywatcher_bridge.py` | Hub-canonical consumer: validates `spiderweb_bridge` records + routes valid ones into `flights`/`track_points`. |
| `schemas/spiderweb_bridge.schema.json` | Shared contract (identical to skywatcher-pr). |
| `tests/test_ingest_skywatcher.py`, `tests/test_no_fr24_modules.py` | Bridge accept/reject + boundary (removed-symbols-absent) gates. |
| `docs/FR24_MIGRATION_TO_SKYWATCHER.md` | Migration note. |

## Zero-hit audit
`grep -rnE "FlightAnalyzer|FlightRadarOCR|process_all_images|process_with_hardening|link_screenshots_to_flights|/mnt/user-data/uploads"` over active `.py` source → **0 hits** (only match: an explanatory comment in `server/backend/main.py`, and the boundary test `tests/test_no_fr24_modules.py`).
