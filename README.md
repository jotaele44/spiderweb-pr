# Puerto Rico Airspace Intelligence System

Flight tracking, mission deduction, and operational intelligence from FlightRadar24 screenshots.

> **Integration status**: integration-ready after validation gates pass. Run `--validate` and review `integration_report.json` before treating outputs as production data.

**Extended docs**: [Architecture](docs/ARCHITECTURE.md) · [Execution Guide](docs/EXECUTION_GUIDE.md) · [Testing](docs/TESTING.md) · [Data Policy](docs/DATA_POLICY.md)

## What it does

Processes 15,000+ FlightRadar24 screenshots via OCR and computer vision to build a searchable flight database, then applies GIS correlation, mission inference, and anomaly detection to produce actionable airspace intelligence for Puerto Rico.

## Architecture

| Phase | File | Purpose |
|-------|------|---------|
| 0 | `pipeline/flight_analyzer.py` | OCR extraction, coordinate mapping, SQLite database |
| 0 | `pipeline/aircraft_intelligence.py` | N-number lookup, operator profiles, mission deduction |
| 1 | `pipeline/ensemble_ocr.py` | 3-engine OCR consensus (Tesseract + PaddleOCR + EasyOCR) |
| 1 | `pipeline/hardening_layer.py` | Confidence scoring, temporal physics validation, job queue |
| 1 | `pipeline/hardened_pipeline.py` | Phase 1 orchestration with provenance and checkpointing |
| 2 | `pipeline/gis_intelligence.py` | Puerto Rico infrastructure graph, corridor analysis, heatmaps |
| 3 | `pipeline/mission_inference.py` | Multi-factor mission scoring, behavioral clustering, Markov prediction |
| 4 | `pipeline/operational_intelligence.py` | Alert engine, daily reports, aircraft profiles |
| — | `run_all.py` | Unified CLI for all phases |
| — | `dashboard/dashboard.jsx` + `dashboard/dashboard.html` | Browser dashboard — 4-tab operational review UI |

### Integration hardening modules

| File | Purpose |
|------|---------|
| `integration/schema_validation.py` | JSON Schema (Draft-7) validation; routes invalid rows to `review_queue.csv` |
| `integration/geo_calibration.py` | Pixel→geographic coordinate conversion with per-result uncertainty metadata |
| `integration/pr_intel_adapter.py` | Exports 6 parquet files + 2 GeoJSON + `source_manifest.json` + `integration_report.json` |
| `integration/ilap_airspace_bridge.py` | POI, ILAP, and corridor candidates as GeoJSON for Spiderweb/UGCN |
| `integration/aasb_airspace_bridge.py` | Airport-node edge CSV and `spiderweb_ingest_manifest.json` |
| `schemas/` | 10 JSON Schema files covering all exported record types |
| `configs/georef_anchors.csv` | 5 PR airport anchor points for georeferencing calibration |

### FR24 screenshot processor modules

| File | Purpose |
|------|---------|
| `fr24/screenshot_inventory.py` | Directory scan with SHA-256 hashing, corrupt detection, duplicate grouping, CSV report |
| `fr24/ui_segmenter.py` | Geometric + edge-detection segmentation of FR24 UI into map/panel/label regions |
| `fr24/route_extractor.py` | HSV color-range masking + 4-connected BFS to extract route polylines from map region |
| `fr24/manual_review_queue.py` | SQLite-backed idempotent queue for low-quality items needing human review |
| `fr24/event_export.py` | Bridge: inventory → screenshots table; routes → track_points table |

## Quick start

```bash
# Install required dependencies
pip install opencv-python pytesseract Pillow numpy

# Install Tesseract OCR (system package)
# Ubuntu: sudo apt-get install tesseract-ocr
# macOS:  brew install tesseract

# Place FlightRadar24 screenshots in uploads directory
# mkdir -p /mnt/user-data/uploads && cp *.jpg /mnt/user-data/uploads/

# Run complete pipeline (all phases)
python run_all.py

# Test with first 10 images only
python run_all.py --images 10

# Show database status
python run_all.py --status

# Generate aircraft intelligence profile
python run_all.py --aircraft N5854Z

# Run specific phase only
python run_all.py --phase 2

# Export DB snapshot for the browser dashboard (lands under outputs/, gitignored)
python run_all.py --export-json outputs/dashboard_data.json

# Open the dashboard (serve from the repo directory so ../outputs/ resolves)
python -m http.server 8080
# then open http://localhost:8080/dashboard/dashboard.html

# ── FR24 screenshot processor ─────────────────────────────────────────────────

# Scan a directory: SHA-256 hash, corrupt detection, duplicate grouping, CSV report
python run_all.py --db flight_database.db --scan-inventory /path/to/screenshots

# Export FR24 events: inventory → screenshots table + routes → track_points table
python run_all.py --db flight_database.db --export-fr24-events /path/to/screenshots

# ── Integration hardening (standalone, runs against existing DB) ──────────────

# Validate all records and route invalids to review_queue.csv
python run_all.py --db flight_database.db --validate

# Export PR Intel parquet + GeoJSON + integration_report.json
python run_all.py --db flight_database.db --export-pr-intel ./outputs/pr_intel

# Export Spiderweb/UGCN bridge files
python run_all.py --db flight_database.db --export-spiderweb ./outputs/spiderweb

# Full integrated run: pipeline + validation + both exports
python run_all.py --images 10 --validate \
  --export-pr-intel ./outputs/pr_intel \
  --export-spiderweb ./outputs/spiderweb

# Check integration gate status
python -c "
import json
r = json.load(open('./outputs/pr_intel/integration_report.json'))
print(r['overall_status'])
for gate, info in r['gates'].items():
    print(f'  {gate}: {info[\"status\"]}')
"
```

## Integration outputs

### `--export-pr-intel <DIR>` produces

| File | Description |
|------|-------------|
| `airspace_events.parquet` | All flights with provenance columns |
| `aircraft_profiles.parquet` | Per-callsign profiles |
| `track_points.parquet` | Track points with provenance |
| `screenshot_evidence.parquet` | Screenshots with sha256, coordinate method, review status |
| `mission_inferences.parquet` | Mission scores |
| `anomaly_index.parquet` | Alerts and anomalies |
| `gis_airspace_features.geojson` | Airport/POI points (EPSG:4326) |
| `route_lines.geojson` | Per-flight origin→dest lines (EPSG:4326) |
| `source_manifest.json` | File list with record counts |
| `integration_report.json` | 6 gate PASS/FAIL status report |

### `--export-spiderweb <DIR>` produces

| File | Description |
|------|-------------|
| `airspace_poi_candidates.geojson` | Recurrence-clustered POI candidates |
| `airspace_ilap_candidates.geojson` | Corridor alignment flight lines |
| `airspace_corridor_candidates.geojson` | POI-pair corridor segments |
| `aasb_airspace_edges.csv` | Airport-node edge list with weights |
| `spiderweb_ingest_manifest.json` | Bridge file inventory |

Every exported record includes provenance: `screenshot_id`, `source_path`, `sha256`, `ocr_confidence`, `coordinate_method`, `coordinate_confidence`, `review_status`. Low-confidence records are routed to `review_queue.csv`.

### `--scan-inventory <DIR>` produces

`screenshot_inventory.csv` (next to the DB) with columns: `path`, `filename`, `size_bytes`, `sha256`, `width`, `height`, `is_corrupt`, `is_duplicate`, `duplicate_of`, `scanned_at`. Summary printed to stdout. Corrupt and duplicate counts are reported; valid images are synced to the `screenshots` DB table.

### `--export-fr24-events <DIR>` produces

Runs the full FR24 event export pipeline over `<DIR>`:
1. Scans and inventories all images (SHA-256, corrupt/dupe detection)
2. Upserts non-corrupt, non-duplicate records into the `screenshots` table
3. Extracts colored route polylines from each valid image
4. Writes extracted route points as rows in the `track_points` table
5. Routes small/low-quality images to the `manual_review_queue` SQLite DB

## Optional: Phase 1 hardening (higher OCR accuracy)

```bash
# PaddleOCR (adds ~50% accuracy improvement)
pip install paddlepaddle paddleocr

# EasyOCR (adds further improvement, requires PyTorch)
pip install torch easyocr
```

Phase 1 automatically falls back to Tesseract-only if these are not installed.

## Key aircraft

| Callsign | Type | Operator | Mission |
|----------|------|----------|---------|
| N5854Z | Airbus H125 | Puerto Rico Electric Power Authority | Power line inspection |
| C6062 | Sikorsky MH-60T | US Coast Guard | Search & Rescue / Maritime Patrol |
| N767PD | Bell 429 | Puerto Rico Police (FURA) | Law enforcement |
| N684JB | Airbus H130 | Private | Charter operations |

## Database queries

```sql
-- All flights for one aircraft
SELECT * FROM flights WHERE callsign = 'N5854Z' ORDER BY takeoff_time DESC;

-- Flight hours by operator
SELECT callsign, COUNT(*) AS flights,
       ROUND(SUM(flight_duration_minutes) / 60.0, 1) AS hours
FROM flights GROUP BY callsign ORDER BY hours DESC;

-- Low-confidence extractions (OCR quality check)
SELECT field_name, AVG(combined_confidence)
FROM extraction_confidence GROUP BY field_name ORDER BY field_name;
```

## Processing time estimates

| Images | Tesseract only | With ensemble OCR |
|--------|---------------|-------------------|
| 10 | ~1 min | ~3 min |
| 100 | ~15 min | ~30 min |
| 1,000 | ~3 h | ~5 h |
| 15,000 | ~45 h | ~65 h |

---

## EarthGPT iOS

Lightweight satellite anomaly detection engine optimized for iOS and a-Shell, co-resident in this repo. See `earthgpt/` for the core package and `scripts/` for 18 single-command pipeline stage runners.

**Pipeline stages**: queue generation → tile sweep → multiscale pass → propagation → seam reconstruction → seam chaining → corridor graph → clustering → cascade refinement → target ranking → GeoJSON export

```bash
pip install requests python-dotenv folium
python scripts/01_generate_queue.py   # start pipeline
```

---

## GEBCO Bathymetry Pipeline

Regional subset extraction and terrain-derivative analysis for the GEBCO 2023 global 15 arc-second bathymetry grid. See `gebco/` for the package.

```bash
pip install numpy scipy xarray netCDF4
python -c "from gebco import open_gebco, subset_region; help(subset_region)"
```

---

## LLM Pipeline (PRUAP Social Data)

RAG index and local LLM query over Puerto Rico UAP/UFO Reddit data. See `llm/prepare_data.py`, `llm/rag_pipeline.py`, `llm/query_llm.py`.

```bash
pip install chromadb sentence-transformers transformers torch accelerate
python llm/prepare_data.py                    # clean + chunk PRUAP_MASTER_SOCIAL.csv
python llm/rag_pipeline.py --build            # build ChromaDB vector index
python llm/query_llm.py "UAP sightings near Aguadilla?"
```
