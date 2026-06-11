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
│   integration/schema_validation.py        JSON Schema Draft-7 record validation
│   integration/pr_intel_adapter.py         Parquet + GeoJSON + integration_report.json
│   integration/ilap_airspace_bridge.py     POI/ILAP/corridor GeoJSON for Spiderweb/UGCN
│   integration/aasb_airspace_bridge.py     Airport-node edge CSV + ingest manifest
│   (FR24 screenshot pipeline — screenshot_inventory, ui_segmenter, route_extractor,
│    manual_review_queue, event_export, ocr_analysis_vector, wave_validator, RLSM suite —
│    migrated to skywatcher-pr; see https://github.com/jotaele44/skywatcher-pr)
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
| `integration/schema_validation.py` | Airspace Intel | |
| `integration/pr_intel_adapter.py` | Airspace Intel | |
| `integration/ilap_airspace_bridge.py` | Airspace Intel | |
| `integration/aasb_airspace_bridge.py` | Airspace Intel | |
| FR24 screenshot pipeline (`screenshot_inventory`, `ui_segmenter`, `route_extractor`, `manual_review_queue`, `event_export`, `ocr_analysis_vector`, `wave_validator`, RLSM suite) | [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr) | Migrated 2026-06 (PRs #110/#111); no longer in this repo |
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

## Status refresh (2026-06, roadmap Themes 2–12)

The system has two mature integration surfaces beyond the phase-0–4 airspace
pipeline:

- **Federation** (`federation/`) — a cross-repo evidence-envelope contract
  (`CONTRACT_VERSION`) with a deterministic correlation hub
  (`federation/hub/query.py`) supporting temporal, normalized-name, spatial, and
  external-id strategies. Live execution is gated by
  `federation/readiness.py` and `federation.json`'s readiness block.
- **RLSM-canonical** — the lossless screenshot mining pipeline (formerly `fr24/` +
  `data/rlsm/`) was the canonical model for FR24 ingestion. It **migrated to
  [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr)** in 2026-06 (PRs
  #110/#111) and is no longer part of this repo.

Cross-cutting layers added across the roadmap: packaging extras +
`pip install -e .` (Theme 1), schema/validation contracts (Theme 2), a
performance layer (WAL/indexes/batch inserts/caching, Theme 4), a coverage
ratchet + lint/type gate (Themes 5–6), GIS/export upgrades incl. native KML
(Theme 7), and observability/security helpers under `pipeline/` (Themes 10–11).

> The `requirements-*.txt` files below are now thin shims over
> `pip install -e ".[extra]"` — see the root README's "Dependencies & extras".
