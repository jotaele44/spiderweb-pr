# Monorepo Architecture

Four independent modules coexist in this repository. They share `tests/`, `outputs/`, and `data/` by convention but have no import-time coupling.

---

## Module map

```
spiderweb-pr/
│
├── ── AIRSPACE INTEL ────────────────────────────────────────────────────────
│   pipeline/flight_analyzer.py          Phase 0: OCR extraction → SQLite
│   pipeline/aircraft_intelligence.py    Phase 0: N-number lookup, operator profiles
│   pipeline/ensemble_ocr.py             Phase 1: 3-engine OCR consensus
│   pipeline/hardening_layer.py          Phase 1: confidence scoring, temporal validation
│   pipeline/hardened_pipeline.py        Phase 1: orchestration + checkpointing
│   pipeline/gis_intelligence.py         Phase 2: PR infrastructure graph, heatmaps
│   pipeline/mission_inference.py        Phase 3: mission scoring, Markov prediction
│   pipeline/operational_intelligence.py Phase 4: alerts, daily reports, profiles
│   run_all.py                  Unified CLI (all phases + exports)
│   integration/geo_calibration.py          Pixel → lat/lon with uncertainty
│   integration/schema_validation.py        JSON Schema Draft-7 record validation
│   integration/pr_intel_adapter.py         Parquet + GeoJSON + integration_report.json
│   integration/ilap_airspace_bridge.py     POI/ILAP/corridor GeoJSON for Spiderweb/UGCN
│   integration/aasb_airspace_bridge.py     Airport-node edge CSV + ingest manifest
│   fr24/screenshot_inventory.py     SHA-256 scan, corrupt/dupe detection
│   fr24/ui_segmenter.py        FR24 screenshot → map/panel/label regions
│   fr24/route_extractor.py          HSV masking + BFS → route polylines
│   fr24/manual_review_queue.py      SQLite-backed low-quality item queue
│   fr24/event_export.py        Inventory + routes → airspace DB
│   fr24/ocr_analysis_vector.py Per-candidate analysis vector + temporal wave grouping
│   fr24/wave_validator.py      Wave physics coherence (altitude, speed, monotonic timestamps)
│   dashboard/dashboard.jsx / .html       4-tab browser dashboard
│   schemas/                    10 JSON Schema files
│   configs/georef_anchors.csv  5 PR airport anchor points
│
├── ── GEBCO BATHYMETRY ──────────────────────────────────────────────────────
│   gebco/
│     __init__.py               Public API re-exports
│     io.py                     open_gebco(), subset_region()
│     terrain.py                slope, curvature, roughness, rugosity
│   pyproject.toml              Package metadata + pinned deps
│   constraints.txt             Exact reproducible pip pins
│
├── ── LLM PIPELINE ──────────────────────────────────────────────────────────
│   llm/prepare_data.py             Clean + chunk PRUAP_MASTER_SOCIAL.csv
│   llm/rag_pipeline.py             Embed chunks → ChromaDB; retrieve top-k
│   llm/query_llm.py                RAG-grounded Q&A CLI (local HF model)
│
├── ── EARTHGPT IOS ──────────────────────────────────────────────────────────
│   earthgpt/                   Core package (24 modules)
│     config.py                 Env / path / threshold config
│     tiles.py                  XYZ tile fetch + cache
│     pipeline.py               Stage orchestration
│     selftest.py               7-gate self-test
│     …                         (see earthgpt/ for full list)
│   scripts/                    18 single-command stage runners
│     grid_sweep_controller_phase1.py
│     grid_sweep_controller_phase2_safe.py
│     reconstruct_seams.py
│     …
│
├── ── SHARED ────────────────────────────────────────────────────────────────
│   tests/                      All module test files (flat, pytest-collected)
│   outputs/                    Runtime artifacts (not committed — see policy)
│   data/                       Input datasets (not committed — see policy)
│   cache/                      Tile / model caches (not committed)
│   tile_cache/                 EarthGPT tile PNG cache (not committed)
│   .github/workflows/ci.yml    Python 3.10/3.11/3.12 CI matrix
│   requirements.txt            Full combined dependency listing
│   requirements-airspace.txt   Airspace-only deps
│   requirements-gebco.txt      GEBCO-only deps
│   requirements-rag.txt        LLM pipeline deps
│   requirements-earthgpt.txt   EarthGPT iOS deps
│   README.md                   Top-level getting-started guide
│   docs/                       Extended documentation
```

---

## Module ownership

| File / Directory | Owned by | Notes |
|-----------------|----------|-------|
| `pipeline/flight_analyzer.py` | Airspace Intel | Core DB writer |
| `pipeline/aircraft_intelligence.py` | Airspace Intel | |
| `pipeline/ensemble_ocr.py` | Airspace Intel | Phase 1, optional |
| `pipeline/hardening_layer.py` | Airspace Intel | Phase 1 |
| `pipeline/hardened_pipeline.py` | Airspace Intel | Phase 1 |
| `pipeline/gis_intelligence.py` | Airspace Intel | Phase 2 |
| `pipeline/mission_inference.py` | Airspace Intel | Phase 3 |
| `pipeline/operational_intelligence.py` | Airspace Intel | Phase 4 |
| `run_all.py` | Airspace Intel | |
| `integration/geo_calibration.py` | Airspace Intel | |
| `integration/schema_validation.py` | Airspace Intel | |
| `integration/pr_intel_adapter.py` | Airspace Intel | |
| `integration/ilap_airspace_bridge.py` | Airspace Intel | |
| `integration/aasb_airspace_bridge.py` | Airspace Intel | |
| `fr24/screenshot_inventory.py` | Airspace Intel | FR24 processor |
| `fr24/ui_segmenter.py` | Airspace Intel | FR24 processor |
| `fr24/route_extractor.py` | Airspace Intel | FR24 processor |
| `fr24/manual_review_queue.py` | Airspace Intel | FR24 processor |
| `fr24/event_export.py` | Airspace Intel | FR24 processor |
| `fr24/ocr_analysis_vector.py` | Airspace Intel | FR24 processor |
| `fr24/wave_validator.py` | Airspace Intel | FR24 processor |
| `dashboard/dashboard.jsx` / `dashboard/dashboard.html` | Airspace Intel | |
| `schemas/` | Airspace Intel | |
| `configs/` | Airspace Intel | |
| `gebco/` | GEBCO Bathymetry | |
| `pyproject.toml` | GEBCO Bathymetry | scoped to `gebco*` |
| `constraints.txt` | GEBCO Bathymetry | |
| `llm/prepare_data.py` | LLM Pipeline | |
| `llm/rag_pipeline.py` | LLM Pipeline | |
| `llm/query_llm.py` | LLM Pipeline | |
| `earthgpt/` | EarthGPT iOS | |
| `scripts/` | EarthGPT iOS | |
| `tests/` | All (flat namespace) | |
| `outputs/` | All (runtime) | not committed |
| `data/` | All (input datasets) | not committed |
| `cache/` | Airspace Intel / EarthGPT | not committed |
| `tile_cache/` | EarthGPT iOS | not committed |
| `.github/workflows/ci.yml` | Shared | |
| `requirements*.txt` | Shared | |
| `docs/` | Shared | |

---

## Dependency isolation

No module imports from another at runtime. Cross-module sharing happens only through:

- **File system**: `outputs/`, `data/`, SQLite DB path
- **CLI flags**: `run_all.py` flags control which sub-systems activate
- **pytest**: all tests collected from `tests/` under one `pytest` run

If you only need one module, install only its requirements file:

```bash
pip install -r requirements-airspace.txt   # airspace intel only
pip install -r requirements-gebco.txt       # GEBCO only
pip install -r requirements-rag.txt         # LLM pipeline only
pip install -r requirements-earthgpt.txt    # EarthGPT only
```
