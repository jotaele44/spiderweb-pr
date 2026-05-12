# Puerto Rico Airspace Intelligence System

Flight tracking, mission deduction, and operational intelligence from FlightRadar24 screenshots.

> **Integration status**: integration-ready after validation gates pass. Run `--validate` and review `integration_report.json` before treating outputs as production data.

## What it does

Processes 15,000+ FlightRadar24 screenshots via OCR and computer vision to build a searchable flight database, then applies GIS correlation, mission inference, and anomaly detection to produce actionable airspace intelligence for Puerto Rico.

## Architecture

| Phase | File | Purpose |
|-------|------|---------|
| 0 | `flight_analyzer.py` | OCR extraction, coordinate mapping, SQLite database |
| 0 | `aircraft_intelligence.py` | N-number lookup, operator profiles, mission deduction |
| 1 | `ensemble_ocr.py` | 3-engine OCR consensus (Tesseract + PaddleOCR + EasyOCR) |
| 1 | `hardening_layer.py` | Confidence scoring, temporal physics validation, job queue |
| 1 | `hardened_pipeline.py` | Phase 1 orchestration with provenance and checkpointing |
| 2 | `gis_intelligence.py` | Puerto Rico infrastructure graph, corridor analysis, heatmaps |
| 3 | `mission_inference.py` | Multi-factor mission scoring, behavioral clustering, Markov prediction |
| 4 | `operational_intelligence.py` | Alert engine, daily reports, aircraft profiles |
| — | `run_all.py` | Unified CLI for all phases |
| — | `dashboard.jsx` + `dashboard.html` | Browser dashboard — 4-tab operational review UI |

### Integration hardening modules

| File | Purpose |
|------|---------|
| `schema_validation.py` | JSON Schema (Draft-7) validation; routes invalid rows to `review_queue.csv` |
| `geo_calibration.py` | Pixel→geographic coordinate conversion with per-result uncertainty metadata |
| `pr_intel_adapter.py` | Exports 6 parquet files + 2 GeoJSON + `source_manifest.json` + `integration_report.json` |
| `ilap_airspace_bridge.py` | POI, ILAP, and corridor candidates as GeoJSON for Spiderweb/UGCN |
| `aasb_airspace_bridge.py` | Airport-node edge CSV and `spiderweb_ingest_manifest.json` |
| `schemas/` | 10 JSON Schema files covering all exported record types |
| `configs/georef_anchors.csv` | 5 PR airport anchor points for georeferencing calibration |

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

# Export DB snapshot for the browser dashboard
python run_all.py --export-json dashboard_data.json

# Open the dashboard (serve from the repo directory)
python -m http.server 8080
# then open http://localhost:8080/dashboard.html

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
