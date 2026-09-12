# Backend Assessment & Development Plan — spiderweb-pr

## Scope & method

Read-only assessment of the backend at `main` (`d4bfb23`, "Refresh skillpack conformance
baseline"). `spiderweb-pr` is the GIS/subsurface/marine/hydrography producer node in the
PRII federation: it covers spatial intelligence across the full Puerto Rico archipelago —
bathymetry (GEBCO), subsurface/karst-adjacent analysis, marine and hydrographic layers,
plus a RAG query surface — and exports a normalized package to `thehub-pr`. Per this repo's
own ADR-0001, the FastAPI service is an explicitly labeled diagnostic-only surface.

## Tech stack & backend inventory

- **Framework**: FastAPI + `aiosqlite`/`sqlite3`, no ORM. Heavy scientific/GIS stack
  (numpy, scipy, pandas, xarray, shapely, scikit-image) plus optional extras for airspace,
  GEBCO bathymetry, RAG (torch/transformers/chromadb/sentence-transformers), EarthGPT,
  imagery MCP, DuckDB spatial, geopandas/rasterio.
- **Storage**: raw SQL, `server/database/schema_sqlite.sql` — flat tables (`agencies,
  vendors, sites, contracts, events, anomalies, sources, investigations, alerts`) with
  JSON-in-TEXT array columns. Migrations via `server/ingestion/migrations.py`, run
  idempotently at FastAPI `lifespan` startup.
- **Endpoints** (`server/backend/main.py`, "PRIIS Backend API" v2.0.0):
  - `/health` (DB integrity check via `PRAGMA integrity_check`)
  - Read-only entity lists: `/agencies`, `/vendors`, `/sites`, `/contracts`, `/events`,
    `/anomalies`, `/sources`, `/investigations`, `/alerts`
  - Pipeline control: `POST /pipeline/run`, `GET /pipeline/status/{job_id}`,
    `GET /pipeline/events/{job_id}` (SSE), `DELETE /pipeline/{job_id}` — spawns `run_all.py`
    as a raw `subprocess.Popen`
  - GeoJSON: `/geo/{layer}.geojson`, `/catalog`, `/spatial/capabilities`, `/spatial/scene`,
    `/spatial/layers`, `/spatial/boundaries/{boundary_id}.geojson`
  - RAG: `POST /rag/query` (SSE, subprocess-wrapped `query_llm.py`),
    `POST /rag/index` (subprocess `rag_pipeline.py`)
  - `server/backend/martin_ingress.py`, `production.py` also present, role relative to
    `main.py` not fully characterized in this pass.
- **Auth**: **none**. CORS locked to `localhost:5173`/`127.0.0.1:5173`; no bearer/token/
  session anywhere in `main.py`. Confirmed intentional per ADR-0001 (diagnostic-only), but
  `POST /pipeline/run` spawns an arbitrary subprocess with zero auth — an RCE-shaped risk
  the moment this leaves localhost, regardless of the diagnostic-only framing.
- **Business/services layer**: `spiderweb/` (enrichment, exports, ingestors,
  remote_monitoring, schemas, spatial [DuckDB engine], subsurface), plus top-level
  `pipeline/`, `integration/`, `readiness/`, `federation/`, `gebco/`, `earthgpt/`,
  `imagery/`, `llm/`, `source_adapters/`. Orchestrated by root `run_all.py` (25.9 KB) and
  `release_check.py`.
- **Background jobs**: in-memory `_jobs: dict` (job_id → `Popen`) in `main.py` — no
  persistence, no queue, no eviction; job state lost on restart.
- **Tests/CI**: 150+ test files (subsurface, marine, hydrography, archipelago, imagery,
  martin/tile-server contracts, RAG pipeline, federation export, GIS intelligence). The
  coverage ratchet in `pyproject.toml` **explicitly excludes `server/*`** ("separate test
  concerns"), so the FastAPI layer itself is not covered by the main ratchet even though
  `test_priis_api.py`/`test_server_smoke.py` exist. 30+ CI workflows including
  `federation-compatibility.yml`, `martin-canary.yml`, `martin-publication-contract.yml`,
  `prii-smoke.yml`, `repo-readiness-policy.yml`, plus many narrow domain gates
  (`pr-hydrography.yml`, `subsurface-santiago-acceptance.yml`, `haf-contract.yml`).

## Completion assessment

- **Fully implemented**: entity read API; GeoJSON layer serving with a catalog-driven
  allowlist; SQLite schema + migrations; spatial boundary registry exposure; large
  domain pipeline/test surface for GIS/ingestion.
- **Partially implemented**: pipeline/RAG execution works but via ad-hoc subprocess with an
  in-memory job registry (no durability); `martin_ingress.py`/`production.py` present but
  their role vs. `main.py` is unclear from static inspection alone.
- **Missing entirely**: any authentication/authorization; a durable job queue; test
  coverage accountability for `server/backend/*` itself (explicitly excluded from the
  ratchet).
- No TODO/FIXME/NotImplementedError/stub markers found in code search.

## Development plan — hardest tasks first

Ordering rationale: item 1 is sequenced first not because it's the most complex to build,
but because `POST /pipeline/run`'s unauthenticated subprocess-spawn is the sharpest concrete
risk in this repo — it should not wait behind harder architectural work. Items 2–3 are then
ordered by genuine engineering/uncertainty difficulty (durable job infra, then a geodetic
correctness problem) before the cross-repo and ML-heavy items, which have external
dependencies outside this repo's control.

1. **Add real auth/authz to `server/backend/main.py`** — Effort: **M**, Urgency:
   **immediate**. Every one of ~20 routes is open, including the subprocess-spawning
   `POST /pipeline/run`. Hard because it's a repo-wide surface change, not a single-endpoint
   fix — should adopt whatever contract `thehub-pr` ships federation-wide (see that repo's
   plan doc) rather than a one-off token, but a temporary shared-secret guard on the
   mutating routes should not wait for that (see Quick wins).
2. **Replace the in-memory `_jobs` registry with a durable job/queue mechanism** — Effort:
   **L**. Needs restart-recovery, concurrency limits, and cancellation for `run_all.py`/
   `rag_pipeline.py`, which are long-running, memory-heavy (torch/transformers) processes
   with no current persistence model.
3. **GEBCO vertical-datum reconciliation gating Cesium terrain** — Effort: **L**, genuine
   unknown. Flagged in-code (comment in `spatial_capabilities()`) as a real geodetic/
   cross-source datum problem, not a pure engineering task — needs domain verification
   before implementation, not just more code.
4. **Complete the Skywatcher boundary closure** (removing remaining FR24/OCR screenshot
   processors per `docs/ADR_SKYWATCHER_SPIDERWEB_INTEGRATION.md`) — Effort: **M**,
   cross-repo. Enforced by a live `docs/DUPLICATION_REGISTER.md` gate
   (`maintenance/adapters/local.py::check_migration_remnants`); needs coordination with
   `skywatcher-pr`'s own plan (see that repo's doc, item on ADR 0006 imagery migration).
5. **Productionize the RAG pipeline** (`/rag/query`, `/rag/index`) — Effort: **L**,
   open-ended. Currently CLI-subprocess-wrapped with no persisted/versioned vector index;
   moving in-process means solving model-load cost, memory footprint, and possibly GPU
   provisioning — an infrastructure decision, not just a refactor.

## Quick wins (sequenced after/alongside the above, not skipped)

- As an interim step before item 1 lands fully, port `thehub-pr`'s `PRII_WRITE_TOKEN`-style
  bearer guard onto the mutating routes (`/pipeline/*`, `/rag/index`) immediately — cheap
  and meaningfully reduces the open-subprocess risk today.
- Add cache headers to static `/geo/{layer}.geojson` responses.
- Audit whether `martin_ingress.py`/`production.py` are dead code or unmounted entry
  points; resolve one way or the other.
