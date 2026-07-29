# Spiderweb canonical GIS frontend

> **Diagnostic-only surface (ADR 0001, Phase 2).** This repo's frontend is a
> development and diagnostic tool for this producer only. The supported product
> surface for the PRII federation is the hub app
> (`thehub-pr/server/frontend`), which renders this producer's data alongside
> the other engines. See `thehub-pr/docs/adr/0001-federated-engines-single-hub.md`.

This is the canonical local UI for the `spiderweb-pr` spatial producer. It
provides a catalog-driven map, feature inspector, evidence-aware timeline,
filters, provenance-preserving GeoJSON/CSV exports, and explicit source or
geometry error states. It is useful for inspecting this engine's own exports in
isolation; it is not the federation's cross-engine product surface.

The UI consumes only Spiderweb's same-origin API:

- `/catalog` describes all available layer families and runtime status.
- `/geo/{layer}.geojson` supplies materialized catalog geometry.
- `/sites`, `/events`, `/anomalies`, and `/sources` populate the workbench.
- `/health` reports backend and database readiness.

Unavailable data is never replaced with demo records. Missing databases,
endpoints, and geometry are visible in the workbench as explicit errors.

## Development

```bash
python -m uvicorn server.backend.gis_app:app --reload --port 8000
```

In a second terminal:

```bash
npm ci
npm run dev
```

The Vite development server proxies the API to `http://127.0.0.1:8000`.

## Verification

```bash
npm run verify
npx playwright install chromium
npm run test:e2e
```

`verify` runs lint, TypeScript, unit tests, the Spiderweb runtime-boundary guard,
and a production build. The guard checks frontend source and JSON, desktop
wiring, the dedicated backend, and the catalog source/generator.
