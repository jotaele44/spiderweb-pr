# Monorepo Architecture

Four independent modules coexist in this repository. They share `tests/`, `outputs/`, and `data/` by convention but have no import-time coupling.

---

## Module map

```
spiderweb-pr/
│
├── ── AIRSPACE INTEL ────────────────────────────────────────────────────────
│   flight_analyzer.py          Phase 0: OCR extraction → SQLite
│   aircraft_intelligence.py    Phase 0: N-number lookup, operator profiles
│   ensemble_ocr.py             Phase 1: 3-engine OCR consensus
│   hardening_layer.py          Phase 1: confidence scoring, temporal validation
│   hardened_pipeline.py        Phase 1: orchestration + checkpointing
│   gis_intelligence.py         Phase 2: PR infrastructure graph, heatmaps
│   mission_inference.py        Phase 3: mission scoring, Markov prediction
│   operational_intelligence.py Phase 4: alerts, daily reports, profiles
│   run_all.py                  Unified CLI (all phases + exports)
│   geo_calibration.py          Pixel → lat/lon with uncertainty
│   schema_validation.py        JSON Schema Draft-7 record validation
│   pr_intel_adapter.py         Parquet + GeoJSON + integration_report.json
│   ilap_airspace_bridge.py     POI/ILAP/corridor GeoJSON for Spiderweb/UGCN
│   aasb_airspace_bridge.py     Airport-node edge CSV + ingest manifest
│   screenshot_inventory.py     SHA-256 scan, corrupt/dupe detection
│   fr24_ui_segmenter.py        FR24 screenshot → map/panel/label regions
│   route_extractor.py          HSV masking + BFS → route polylines
│   manual_review_queue.py      SQLite-backed low-quality item queue
│   fr24_event_export.py        Inventory + routes → airspace DB
│   dashboard.jsx / .html       4-tab browser dashboard
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
│   prepare_data.py             Clean + chunk PRUAP_MASTER_SOCIAL.csv
│   rag_pipeline.py             Embed chunks → ChromaDB; retrieve top-k
│   query_llm.py                RAG-grounded Q&A CLI (local HF model)
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
| `flight_analyzer.py` | Airspace Intel | Core DB writer |
| `aircraft_intelligence.py` | Airspace Intel | |
| `ensemble_ocr.py` | Airspace Intel | Phase 1, optional |
| `hardening_layer.py` | Airspace Intel | Phase 1 |
| `hardened_pipeline.py` | Airspace Intel | Phase 1 |
| `gis_intelligence.py` | Airspace Intel | Phase 2 |
| `mission_inference.py` | Airspace Intel | Phase 3 |
| `operational_intelligence.py` | Airspace Intel | Phase 4 |
| `run_all.py` | Airspace Intel | |
| `geo_calibration.py` | Airspace Intel | |
| `schema_validation.py` | Airspace Intel | |
| `pr_intel_adapter.py` | Airspace Intel | |
| `ilap_airspace_bridge.py` | Airspace Intel | |
| `aasb_airspace_bridge.py` | Airspace Intel | |
| `screenshot_inventory.py` | Airspace Intel | FR24 processor |
| `fr24_ui_segmenter.py` | Airspace Intel | FR24 processor |
| `route_extractor.py` | Airspace Intel | FR24 processor |
| `manual_review_queue.py` | Airspace Intel | FR24 processor |
| `fr24_event_export.py` | Airspace Intel | FR24 processor |
| `dashboard.jsx` / `dashboard.html` | Airspace Intel | |
| `schemas/` | Airspace Intel | |
| `configs/` | Airspace Intel | |
| `gebco/` | GEBCO Bathymetry | |
| `pyproject.toml` | GEBCO Bathymetry | scoped to `gebco*` |
| `constraints.txt` | GEBCO Bathymetry | |
| `prepare_data.py` | LLM Pipeline | |
| `rag_pipeline.py` | LLM Pipeline | |
| `query_llm.py` | LLM Pipeline | |
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

---

## Phase 9 — Cross-Module Integration Bridges

These bridges connect the four modules at runtime without creating import-time coupling. All bridges are opt-in; modules remain independently runnable.

### Bridge Map

| Bridge | From | To | Mechanism |
|--------|------|----|-----------|
| ILAP → EarthGPT | `ilap_airspace_bridge.py` | `earthgpt/context.py` | `TileContext.from_flight_event()` converts ILAP corridor → tile context |
| PRIntelAdapter 7th gate | `pr_intel_adapter.py` | `earthgpt/pipeline.py` | `earthgpt_dry_run_pass` gate calls `dry_run(nodes)` |
| GIS + GEBCO depth | `gis_intelligence.py` | `gebco/terrain.py` | `mona_passage_profile()` annotates maritime chokepoints with depth |
| Mission → RAG | `mission_inference.py` | `rag_pipeline.py` | UNKNOWN missions trigger `RAGPipeline` query appended as `rag_context` |
| Alerts + Corridor | `operational_intelligence.py` | `earthgpt/corridor_graph.py` | `Critical Infrastructure Proximity` alert fires when corridor overlaps PREPA |
| Calibration + Metrics | `calibrate_scoring.py` | `earthgpt/metrics.py` | EarthGPT pipeline latency feeds calibration signal |

### Selective Module Execution

Use `run_all.py --module <list>` to run only specific modules:

```bash
python run_all.py --db data.db --module airspace          # Airspace Intel only
python run_all.py --db data.db --module airspace,gebco    # Airspace + GEBCO
python run_all.py --db data.db --module airspace,gebco,rag,earthgpt  # all
```

Accepted names: `airspace`, `gebco`, `rag`, `earthgpt`
