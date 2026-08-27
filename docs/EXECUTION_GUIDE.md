# Execution Guide

Smoke commands and full workflows for each module. All commands run from the repo root.

---

## Prerequisites

```bash
# Clone and enter
git clone https://github.com/jotaele44/spiderweb-pr.git
cd spiderweb-pr

# Install module deps (choose one or all)
pip install -r requirements-airspace.txt
pip install -r requirements-gebco.txt
pip install -r requirements-rag.txt
pip install -r requirements-earthgpt.txt
```

---

## Spiderweb Pipeline

### Smoke commands

```bash
# Verify install and inspect an existing validated database
python run_all.py --help
python run_all.py --db /path/to/validated.db --status

# Schema validation on an existing DB
python run_all.py --db /path/to/validated.db --validate

# PR Intel export
python run_all.py --db /path/to/validated.db --export-pr-intel /tmp/pr_intel_smoke
python -c "
import json
r = json.load(open('/tmp/pr_intel_smoke/integration_report.json'))
print(r['overall_status'])
"

# Spiderweb bridge export
python run_all.py --db /path/to/validated.db --export-spiderweb /tmp/sw_smoke
ls /tmp/sw_smoke/
```

### Downstream pipeline

Spiderweb no longer creates flight/track databases from screenshots. Phases 2-4
remain available for an already validated database containing `flights` and
`track_points`. A read-only preflight rejects missing or incomplete databases
before any derived tables are written.

```bash
# Run all retained downstream phases
python run_all.py --db /path/to/validated.db

# Run one retained phase
python run_all.py --db /path/to/validated.db --phase 2

# Validate and export without running phases
python run_all.py --db /path/to/validated.db --validate \
  --export-pr-intel outputs/pr_intel --export-spiderweb outputs/spiderweb
```

### FR24 screenshot processor

The FR24 screenshot ingestion pipeline (inventory scan, route extraction, RLSM mining)
**migrated to [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr)** in 2026-06
(PRs #110/#111). Spiderweb contains no active OCR runner or screenshot-processing
phase. A direct package consumer is also absent until the four prerequisites in
`ADR_SKYWATCHER_SPIDERWEB_INTEGRATION.md` pass.

### Reports and profiles

```bash
# Daily operational report
python run_all.py --db outputs/flights.db --report daily

# Aircraft intelligence profile
python run_all.py --db outputs/flights.db --aircraft N5854Z

```

---

## GEBCO Bathymetry Pipeline

### Smoke commands (no real data required)

```bash
# Verify package import
python -c "from gebco import open_gebco, subset_region, compute_slope; print('GEBCO OK')"

# Run synthetic unit tests
python -m pytest tests/test_io.py tests/test_terrain.py -v
```

### Full pipeline (requires GEBCO_2023.nc)

```bash
# Download GEBCO 2023 (15 arc-second global grid, ~7 GB)
# https://www.gebco.net/data_and_products/gridded_bathymetry_data/

python - <<'EOF'
from gebco import open_gebco, subset_region, compute_slope, cell_size_meters

ds = open_gebco("data/GEBCO_2023.nc")

# Puerto Rico region
elev = subset_region(ds, lat_min=17.5, lat_max=18.6, lon_min=-67.5, lon_max=-65.2)
dx, dy = cell_size_meters(18.05)  # mid-latitude
slope, _, _ = compute_slope(elev.values.astype(float), dx, dy)

print(f"Elevation shape: {elev.shape}")
print(f"Slope range: {slope.min():.2f}° – {slope.max():.2f}°")
EOF
```

---

## LLM Pipeline (PRUAP Social Data)

### Smoke commands (no CSV required)

```bash
python -c "import chromadb, sentence_transformers, transformers; print('LLM deps OK')"
```

### Full pipeline (requires PRUAP_MASTER_SOCIAL.csv)

```bash
# Step 1: Clean and chunk the social data
python llm/prepare_data.py --input data/PRUAP_MASTER_SOCIAL.csv
# produces: chunks.jsonl

# Step 2: Build ChromaDB vector index
python llm/rag_pipeline.py --build --chunks chunks.jsonl --db outputs/pruap_index

# Step 3: Query with RAG
python llm/query_llm.py "UAP sightings near Aguadilla?" --db outputs/pruap_index

# Fine-tuning format instead of RAG chunks
python llm/prepare_data.py --input data/PRUAP_MASTER_SOCIAL.csv --finetune
# produces: finetune.jsonl

# Query without RAG context (LLM only)
python llm/query_llm.py "What USO sightings exist near Puerto Rico?" --no-context
```

---

## EarthGPT iOS

### Smoke commands

```bash
# Verify package and run self-test (7 gates, no tile fetch needed)
python -c "
from earthgpt.selftest import run_selftest
results = run_selftest()
print(f'{results[\"passed\"]}/{results[\"total\"]} self-test gates passed')
"

# Run EarthGPT unit tests
python -m pytest tests/test_metrics.py tests/test_seams.py tests/test_pipeline.py -v
```

### Full pipeline (requires tile access)

```bash
# Step 1: Generate a queue (CSV bounding box or PR grid fallback)
python scripts/make_geo_grid_queue.py         # produces outputs/queue.jsonl

# Step 2: Phase 1 tile sweep
python scripts/grid_sweep_controller_phase1.py

# Step 3: Multiscale pass
python scripts/run_multiscale.py

# Step 4: Score propagation
python scripts/run_propagation.py

# Step 5: Seam reconstruction + chaining
python scripts/reconstruct_seams.py
python scripts/seam_chain_builder.py

# Step 6: Corridor graph + clustering
python scripts/run_corridor_graph.py
python scripts/build_clusters.py

# Step 7: Cascade refinement + ranking
python scripts/cascade_refine.py
python scripts/run_target_ranker.py

# Step 8: Export GeoJSON
python scripts/export_ranked_geojson.py
# produces: outputs/ranked_targets.geojson
```

All scripts are resumable: re-running after interruption picks up from the last completed JSONL entry.

---

## Running all tests

```bash
# Full suite (GEBCO tests require xarray + scipy)
python -m pytest tests/ -q

# Skip GEBCO (no xarray installed)
python -m pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py

# Module-scoped runs (single line — iOS / a-Shell friendly)
python -m pytest tests/test_aircraft_intelligence.py tests/test_cli.py tests/test_end_to_end.py tests/test_gis_intelligence.py tests/test_mission_inference.py tests/test_ocr_confidence.py tests/test_pr_intel_adapter.py tests/test_schema_validation.py tests/test_screenshot_inventory.py tests/test_spiderweb_bridge.py tests/test_temporal_validator.py -q  # Spiderweb: 99 tests

python -m pytest tests/test_io.py tests/test_terrain.py -q  # GEBCO: 39 tests
python -m pytest tests/test_metrics.py tests/test_seams.py tests/test_pipeline.py -q  # EarthGPT: 19 tests
```
