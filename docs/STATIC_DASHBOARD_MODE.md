# Static-first dashboard mode

The static dashboard mode lets operators review Spiderweb/FR24/Contract-Finance outputs without hosting the FastAPI server.

## Operating model

```text
Python CLI / pipeline outputs -> outputs/*.json + outputs/*.geojson -> static dashboard bundle
```

This mode is read-only and export-driven. It is intended for review, briefing, and portable dashboard handoff. It does not start, stop, or stream pipeline jobs.

## Build the bundle

From the repository root:

```bash
python scripts/export_static_dashboard.py --dist dist/static-dashboard --outputs outputs
```

If `outputs/dashboard_data.json` does not exist, generate it from an existing SQLite DB:

```bash
python scripts/export_static_dashboard.py \
  --db ~/flight_database.db \
  --outputs outputs \
  --dist dist/static-dashboard
```

The exporter writes:

```text
dist/static-dashboard/
├── index.html
├── dashboard.jsx
├── dashboard_temporal_waves.jsx
├── dashboard_contract_finance.jsx
├── outputs/
│   ├── dashboard_data.json
│   ├── fr24_dashboard_review_queue.json              # optional
│   ├── fr24_temporal_wave_dashboard.json             # optional
│   ├── contract_finance_layer_report.json            # optional
│   └── contract_finance_scored_overlay.geojson       # optional
└── static_dashboard_manifest.json
```

## Open locally

Most browsers restrict `fetch()` from `file://` URLs. Use a temporary local static file server from inside the bundle directory:

```bash
cd dist/static-dashboard
python -m http.server 8080
```

Then open:

```text
http://localhost:8080
```

This is not a deployed backend. It only serves local static files so the browser can load JSON and GeoJSON outputs.

## What works without FastAPI

| Capability | Static mode |
|---|---|
| Review dashboard output | yes |
| FR24 review queue display | yes, when exported |
| Temporal wave overlay | yes, when exported |
| Contract-Finance overlay | yes, when exported |
| GitHub Pages/static hosting | yes, after bundle creation |
| Run pipeline from UI | no |
| Stop pipeline from UI | no |
| Stream pipeline logs | no |
| Live RAG query | no |

## Validation

Run the static export smoke tests:

```bash
python -m pytest tests/test_static_dashboard_export.py -v
```

The tests verify that required dashboard assets are copied, output fetch paths are rewritten to `./outputs/`, and missing `dashboard_data.json` fails hard instead of creating a broken bundle.
