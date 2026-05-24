# Test Matrix

All tests live in `tests/` and are collected by a single `pytest` invocation. Tests are organized by module but share fixtures via `tests/conftest.py`.

---

## Quick reference

```bash
# Full suite
python -m pytest tests/ -q

# With GEBCO (requires xarray + scipy in a clean virtualenv)
python -m pytest tests/ -q

# Without GEBCO (system Python without xarray)
python -m pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py
```

---

## Test file → module mapping

### Airspace Intelligence System (123 tests)

| Test file | What it covers |
|-----------|---------------|
| `test_aircraft_intelligence.py` | N-number lookup, operator profile deduction, unknown callsign handling |
| `test_cli.py` | `run_all.py --status`, `--export-json` CLI flags |
| `test_end_to_end.py` | Full `--validate`, `--export-pr-intel`, `--export-spiderweb` smoke runs |
| `test_fr24_bridge.py` | `FR24EventExporter`, `ManualReviewQueue` adapter compatibility |
| `test_fr24_inventory.py` | `ScreenshotInventory`: scan, SHA-256, corrupt detection, dedup, CSV report |
| `test_geo_calibration.py` | `GeoCalibration` 3 modes, `CoordResult`, `pixel_to_coord`, `in_pr_bbox` |
| `test_gis_intelligence.py` | Haversine distance, corridor membership, PR infrastructure graph |
| `test_mission_inference.py` | Mission scorer probabilities, confidence levels, multi-factor weights |
| `test_ocr_confidence.py` | Confidence thresholds, low-confidence routing to review queue |
| `test_pr_intel_adapter.py` | All 10 required output files created, gate status in integration_report.json |
| `test_route_extractor.py` | `RouteExtractor`, `FR24UISegmenter`, synthetic orange route extraction |
| `test_schema_validation.py` | Valid/invalid record routing, `review_queue.csv` output |
| `test_screenshot_inventory.py` | Screenshots table column coverage after sync_to_db |
| `test_spiderweb_bridge.py` | ILAP + AASB bridge: 5 output files created, manifest structure |
| `test_temporal_validator.py` | Physics-violation detection (speed, altitude jumps) |
| `test_fr24_analysis_vector.py` | Analysis vector columns, quality tiers, temporal parsing, wave grouping |
| `test_fr24_wave_validator.py` | Wave physics checks (climb rate, speed, monotonic timestamps) |

### GEBCO Bathymetry (39 tests) — requires xarray, scipy, netCDF4

| Test file | What it covers |
|-----------|---------------|
| `test_io.py` | `open_gebco` (missing variable, ascending/descending lat), `subset_region` (bounds, dtype, empty guard, xarray issue #1613) |
| `test_terrain.py` | `cell_size_meters`, `compute_slope` (flat, ramp, Horn kernel), `compute_curvatures` (Z&T 1987), `compute_roughness` (O(N) variance identity), `compute_rugosity` (area_ratio + VRM) |

### LLM Pipeline — PRUAP Social Data (52 tests)

Optional-dependency tests use `pytest.importorskip`; they skip cleanly without `chromadb` or `torch` installed.

| Test file | What it covers |
|-----------|---------------|
| `test_prepare_data.py` | `load_csv`, `clean_rows` (dedup, length filter, numeric cast), `to_chunks` (JSONL structure, metadata keys), `to_finetune` (prompt/completion format) |
| `test_rag_pipeline.py` | `format_context` (empty, single, multi, missing-key fallback), `get_collection` (name, idempotent), `build_index` (missing file → SystemExit, upsert called), `retrieve` (hits structure, score in [0,1]) |
| `test_query_llm.py` | `build_prompt` (question included, context section, `### Answer` marker), `get_context` (missing DB → None, calls retrieve+format, empty hits → None), `generate` (new-token slicing, whitespace strip, max_new_tokens), constants |

### EarthGPT iOS (19 tests)

| Test file | What it covers |
|-----------|---------------|
| `test_metrics.py` | Anomaly metric computation, edge cases |
| `test_seams.py` | Seam reconstruction and chaining |
| `test_pipeline.py` | Stage orchestration, resumability |

---

## Fixtures (`tests/conftest.py`)

| Fixture | Scope | Provides |
|---------|-------|---------|
| `tmp_output` | function | Temporary directory for test output files |
| `populated_db` | function | SQLite DB with 3 flights (N5854Z/PREPA, C6062/USCG, N767PD/FURA), 5 track_points each, 3 screenshots each (ocr_confidence=0.85, coordinate_method="fixed_pr_bounds"), 1 alert each, 1 mission_score each |

---

## CI matrix

`.github/workflows/ci.yml` has two independent jobs that run on every push and PR against `main`:

### Job: `test` — Airspace Intel + LLM Pipeline + EarthGPT

Python versions: **3.10**, **3.11**, **3.12**  
Dependencies: `jsonschema>=4.17`, `pyarrow>=14.0`, `pytest>=7.4`, `Pillow>=10.0`, `numpy>=1.26`

| Step | Command |
|------|---------|
| Syntax check | `python -m py_compile *.py` |
| Test suite | `python -m pytest tests/ -q --tb=short --ignore=tests/test_io.py --ignore=tests/test_terrain.py` |
| EarthGPT selftest | `run_selftest()` — asserts 7/7 gates pass |
| CLI smoke — status | `python run_all.py --db /tmp/ci_smoke.db --status` |
| CLI smoke — validate | `python run_all.py --db /tmp/ci_smoke.db --validate` |
| CLI smoke — export-pr-intel | Full gate assertion on `integration_report.json` (6 gates) |
| CLI smoke — export-spiderweb | File existence checks |

### Job: `test-gebco` — GEBCO Bathymetry

Python versions: **3.11**, **3.12**  
Dependencies: `requirements-gebco.txt` (numpy, scipy, xarray, netCDF4, pandas, …)

| Step | Command |
|------|---------|
| GEBCO test suite | `python -m pytest tests/test_io.py tests/test_terrain.py -v --tb=short` |

---

## Adding tests for a new feature

1. Drop a `test_<feature>.py` file in `tests/`
2. Use `tmp_path` (built-in) for temporary files, `populated_db` for a pre-seeded DB
3. Use `pytest.importorskip("numpy")` for optional-dependency tests — never `skipif(True, ...)`
4. Run `python -m pytest tests/test_<feature>.py -v` before pushing
