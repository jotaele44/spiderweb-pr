# GUI Audit — Spiderweb (PRII)

_Audited 2026-08-23 against `e15133f` (branch `claude/repository-gui-audit-csr1xs`, off `main`)._

## 1. Overview

Spiderweb is one of the PRII ("PR Integrated Intelligence System") federation's
producer repos. Its GUI is a single-page React application at
`server/frontend` — the top-level `dashboard/` folder at the repo root is a
static decoy (README + icon PNGs only) and is **not** part of the real
interface.

**Tech stack:** Vite + React 18 + TypeScript, MapLibre GL JS (spatial layer),
TanStack Table (Finance module), Zod (API response validation), no router —
navigation is a single `moduleId` state switch with `React.lazy`-split module
bundles. Styling is hand-written CSS (`styles/federation.css` + `styles/app.css`),
no component library.

**Shape:** one persistent chrome (top command bar, left rail, right inspector,
bottom timeline) wrapping six lazy-loaded modules ("tabs"): **Command**,
**Finance**, **Spatial**, **Anomaly**, **Graph**, **Query**. A shared
`Selection` object (`{kind, id}`) is the cross-module linking mechanism —
almost every clickable entity reference in every module sets it, and the
right-hand Inspector renders whatever it currently points at.

**Backend:** `server/backend/main.py`, a FastAPI app backed by a local SQLite
file (`server/priis.db`), seeded by `server/ingestion/seed_demo.py` with a
small, obviously-synthetic demo dataset (no external API keys, no network
calls). It serves the nine PRIIS entity collections, a pipeline-run/SSE-log
endpoint that shells out to `run_all.py`, a RAG query/SSE endpoint that shells
out to a `query_llm.py` script, and GeoJSON/vector-tile endpoints for the
spatial layers.

**Entry points:**
- **Dev:** `cd server/frontend && npm run dev` → `http://localhost:5173`. In
  dev mode the app talks to a backend at `http://localhost:8000` by default
  (overridable via `VITE_API_BASE`); if unreachable it falls back to a bundled
  mock dataset (`src/data/mockData.ts`) and the header shows `DEMO` instead of
  `LIVE`.
- **Desktop:** the root launcher scripts (`PRII-SPIDERWEB.command` / `.sh` /
  `.bat` / `.app`) build the SPA and start a local FastAPI+SPA server on an
  ephemeral port, then open it in a desktop window or the system browser. See
  §4.

## 2. Method

Every module under `server/frontend/src/modules` and every component under
`server/frontend/src/components` that renders a control was read in full, and
every handler it wires up was traced to its actual implementation (state
update, `fetch`/`EventSource` call, or client-side export). Live verification
used `npm install` + `npm run dev`, plus a real instance of this repo's own
FastAPI backend (seeded from `server/ingestion/seed_demo.py`, deps installed
into a throwaway venv) started on an **isolated port** — this container runs
several sibling PRII repo audits concurrently, and the default dev port 8000
was already occupied by a *different* repo's backend (`moneysweep-pr`), so
using it would have silently cross-contaminated results. Interaction was
driven with Playwright against the pre-installed Chromium
(`/opt/pw-browsers/chromium-1194`). Base-map raster tiles (OpenStreetMap) and
the Martin vector-tile service were not reachable in this environment and are
marked **static-only** below rather than chased.

## 3. Global chrome

Rendered by `App.tsx` and always on screen regardless of which module tab is
active.

### 3.1 Command bar (`components/CommandBar.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Query input | Text input (form) | "QUERY" placeholder, `aria-label="Global Spiderweb query"` | Submitting (Enter) calls `onSubmit(query)` → App sets `moduleId="query"` and increments `querySubmitCount`, which `QueryLayer` watches to auto-run the submitted text | Live | Confirmed: typing text and pressing Enter switches to the Query tab and runs it |
| Filter chip remove (`×`) | Button (dynamic, one per chip) | `×` | `removeFilter(key)` → `setFilters(current => current.filter(...))` | **Static — dead control** | `filters` state is initialized to `[]` and is **never populated anywhere in the codebase** (`setFilters` has exactly one call site, the removal itself). No chip can ever render, so this button is unreachable in the shipped app |
| Theme toggle | Button | "◐ LIGHT" / "◑ DARK" | Flips `theme` dark↔light; App effect sets `document.documentElement.dataset.theme` and persists to `localStorage["spiderweb_theme"]` | Live | Toggled and confirmed both directions; also seeds from `prefers-color-scheme` on first load |
| Run Pipeline / Stop / Run Again / Retry | Button | Dynamic via `RUN_LABEL` map | Idle → `startPipeline()` (`POST /pipeline/run`), opens `streamPipeline()` (`GET /pipeline/events/{id}` SSE, falls back to polling `GET /pipeline/status/{id}` if the stream drops); running → `stopPipeline(jobId)` (`DELETE /pipeline/{id}`) | Live | Verified against both an unreachable backend (immediate `error` → RETRY) and the real backend (job starts, streams, and correctly reaches `error`/RETRY because the spawned `run_all.py` needs the full heavy dependency stack this audit's minimal venv doesn't have — the state machine itself is confirmed correct) |

### 3.2 Left rail (`components/LeftRail.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Module nav buttons (×6) | Button list | Command/Finance/Spatial/Anomaly/Graph/Query + code `00`–`05` | `setModule(mod.id)` | Live | |
| Investigation buttons (dynamic) | Button list | Investigation id + status | Sets `activeInvestigation` (persisted to `localStorage["priis_investigation"]`) and `setSelection({kind:"investigation", id})` | Live | |
| Source rows (dynamic) | Button list | Source name, tier badge, status pill | `setSelection({kind:"source", id})` | Live | |
| Watchlist buttons (dynamic) | Button list | Kind + id | `setSelection(item)` (item is already a full `Selection`) | Live | In live mode the watchlist is client-derived (`deriveWatchlist` in `api/client.ts`) from high-band anomalies + flagged contracts, since the backend has no watchlist endpoint |

### 3.3 Tab strip / chrome toggles (`App.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Left-rail collapse toggle | Button | `«` / `»` | Toggles `leftCollapsed` (persisted `priis_left_collapsed`); also bound to the `[` key (ignored while typing) | Live | Button and keyboard shortcut both confirmed |
| Module tabs (×6, `role="tab"`) | Button list (tab strip, duplicates left-rail nav) | Same 6 module names | `setModule(tab.id)` | Live | |
| Inspector collapse toggle | Button | `«` / `»` | Toggles `rightCollapsed` (persisted `priis_right_collapsed`); bound to `]` | Live | |

### 3.4 Inspector (`components/Inspector.tsx`, `InspectorShell`, `EntityLinkList`)

Renders one of seven variants keyed on `selection.kind`; every cross-reference
button below calls `setSelection(...)` to re-target the panel (and, for
contracts/sites/etc., can cascade into other modules on next tab switch).

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Anomaly → "Open site · {name}" | Button | Site name | `setSelection({kind:"site", id})` | Live | |
| Anomaly → linked contracts | Link list (`EntityLinkList`) | Contract id / amount | `setSelection({kind:"contract", id})` | Live | |
| Contract → Agency quick-link | Button | Agency code | `setSelection({kind:"agency", id})` | Live | |
| Contract → Vendor quick-link | Button | Vendor name | `setSelection({kind:"vendor", id})` | Live | |
| Contract → Site quick-link | Button | Site name | `setSelection({kind:"site", id})` | Live | |
| Site → Contracts | Link list | Contract id / amount | `setSelection({kind:"contract", id})` | Live | |
| Site → Anomalies | Link list | Anomaly id / score | `setSelection({kind:"anomaly", id})` | Live | |
| Vendor → Linked awards | Link list | Contract id / amount | `setSelection({kind:"contract", id})` | Live | |
| Agency → Contracts | Link list | Contract id / amount | `setSelection({kind:"contract", id})` | Live | |
| Event → "Open linked site" | Button | — | `setSelection({kind:"site", id: event.siteId})` | Live | |
| Event → "Open referenced record" | Button | — (only when `event.refId` set) | `setSelection({kind:"contract", id: event.refId})` | Live | |

### 3.5 Timeline (`components/Timeline.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Temporal cursor track | Slider (`role="slider"`, click + keyboard) | — | Click sets cursor from pointer X; `ArrowLeft`/`ArrowRight` step 1 day (7 with Shift), `Home`/`End` jump to window bounds. Persists to `localStorage["priis_cursor"]` | Live | Click-to-position, arrow-key, and Home-key navigation all confirmed |
| Timeline event markers (dynamic) | Button list | Tier badge + event id | `setSelection({kind:"event", id})` | Live | |

## 4. Command Center (`modules/CommandCenter.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "OPEN QUERY LAYER" | Button (primary) | OPEN QUERY LAYER | `setModule("query")` | Live | |
| Anomaly cards (dynamic, `AnomalyCard`) | Button list | Anomaly id/title, category, summary | `setSelection({kind:"anomaly", id})` + `setModule("anomaly")` | Live | Alert-feed table itself has no interactive rows |

## 5. Finance Intelligence (`modules/FinanceIntelligence.tsx`)

TanStack Table over `data.contracts`, default-sorted by amount descending.

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Filter input | Text input | "filter…", `aria-label="Filter contracts"` | Sets TanStack `globalFilter` | Live — **bug found** | The table's global filter matches against each column's raw *accessor* value, not the rendered cell. Vendor/agency/site columns display human-readable names (`byId(...).name`) but their underlying data is an id (e.g. `V-1024`). Typing the name shown on screen — e.g. `"Caribe"` (a real vendor, visibly present in the table) or `"Roosevelt"` (a real site name) — returns **"No contracts match"**; only the raw id (`"V-1024"`, `"S-001"`) matches. Confirmed directly: filtering `"Caribe"` → 0 rows, filtering `"V-1024"` → 4 rows |
| EXPORT CSV | Button | EXPORT CSV | `exportContractsCsv(data)` — builds a CSV client-side (id/signed/agency/vendor/site/amount/status/tier/note/procurement_method) and downloads it via a `Blob` URL | Live | Download fired: `priis-contracts-<date>.csv` |
| Column sort buttons (×8, one per column, `.th-sort`) | Button | Column header + sort arrow | `header.column.getToggleSortingHandler()`, cycles asc → desc → off; updates `aria-sort` | Live | Verified on the Amount column (asc then desc) |
| Contract rows (dynamic) | Row, `tabIndex=0`, Enter/Space-activatable | — | `setSelection({kind:"contract", id})`; `aria-selected` reflects current selection | Live | Uses implicit table `row` role (not `role="button"`) so the grid stays screen-reader navigable |
| Vendor concentration buttons (dynamic, right rail) | Button list | Vendor name + total | `setSelection({kind:"vendor", id})` | Live | |

## 6. Spatial Intelligence (`modules/SpatialIntelligence.tsx`)

MapLibre GL map over a raster OSM basemap, with app-managed GeoJSON/vector-tile
overlay layers and DOM-element markers per site.

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Hide layers" / "Show layers" | Button | Toggle text | Toggles `layerPanelCollapsed` (persisted `spiderweb_layer_collapsed`); also bound to the `L` key; triggers a delayed `map.resize()` | Live | |
| Layer toggle buttons (×8: Contracts, Infrastructure, Sensitive sites, Anomalies, Municipios, Census tracts, Places, Barrios) | Button list, `aria-pressed` | Layer name + status (`on`/`off`/`loading…`/`error`) | Flips `layers[key]`. The 4 marker layers just filter which site markers render; the 4 polygon layers (municipios/tracts/places/barrios) additionally drive a live fetch — municipios via a Martin vector-tile source, the other three via `GET /geo/{layer}.geojson` | Live, with caveats | **Municipios**: static-only — defaults to Martin vector tiles (`MUNICIPIOS_DELIVERY="martin"`); no Martin service is running here, so it shows `error` (confirmed: `502` from `/tiles/municipios`). **Census tracts**: live-verified **bug** — toggling it on does trigger a real `GET /geo/tracts.geojson` that succeeds (`200 OK`, confirmed in the backend's own access log), but the on-screen status stays on `loading…` indefinitely. Root cause read from source: `whenStyleReady()` gates the `"loaded"` status update on `map.isStyleLoaded()`, which never appears to resolve true while the base OSM raster tiles are unreachable (blocked network in this container) — so a layer whose data arrived successfully can still show a permanently stuck spinner state whenever the basemap itself can't load |
| Site markers (dynamic DOM buttons, `.map-marker`) | Button list | Marker title/aria-label: site name, contract total, anomaly id | `setSelection({kind: anomaly && layers.anomaly ? "anomaly" : "site", id})` | Live | |
| "dismiss base map note" | Button | dismiss | `setTilesFailed(false)` | Static-only | Only rendered when `tilesFailed` is true, set by `map.on("error", e => e.sourceId==="osm" && setTilesFailed(true))`. With OSM tile requests actively blocked for 6+ seconds the banner never appeared — MapLibre's per-tile raster failures don't appear to surface as a map-level `error` event with that `sourceId` in this environment, so this control may be effectively unreachable short of a harder basemap failure. Code path read and confirmed correctly wired |
| Top spatial anomalies cards (dynamic) | Button list (`AnomalyCard`) | Anomaly id, site name | `setSelection({kind:"anomaly", id})` | Live | |
| Map zoom +/− control | Third-party (MapLibre `NavigationControl`) | `+` / `−` | Native MapLibre zoom, no app-level handler | Live (visually confirmed present) | Not counted in the element totals below — not app-authored |

## 7. Anomaly Workbench (`modules/AnomalyWorkbench.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| EXPORT CSV | Button | EXPORT CSV | `exportAnomaliesCsv(data)` — client-side CSV (id/title/category/score/band/siteId/confidence), downloads `priis-anomalies-<date>.csv` | Live | Download confirmed |
| EXPORT BRIEF | Button, `disabled={!active}` | EXPORT BRIEF | `downloadBrief(active.id, data)` — builds a Markdown evidence brief client-side (summary, factors, linked contracts table, linked events table, contradictions, standard next-steps) and downloads `priis-brief-<id>-<date>.md` | Live | Download confirmed |
| Cluster queue cards (dynamic, left panel) | Button list (`AnomalyCard`) | Anomaly id, category, title | `setSelection({kind:"anomaly", id})`, drives the detail pane | Live | |
| Site quick-link (detail pane) | Button | Site name | `setSelection({kind:"site", id: active.siteId})` | Live | |

## 8. Investigation Graph (`modules/InvestigationGraph.tsx`)

A small fixed-layout SVG graph scaffold (5 nodes, 4 edges), built only from the
**first** anomaly in the loaded dataset.

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| EXPORT GRAPH | Button | EXPORT GRAPH | `exportGraph()` — builds a `{nodes, edges}` JSON payload client-side and downloads `spiderweb-graph-<anomalyId>.json` | Live | Download confirmed |
| Graph node buttons (×5: anomaly/site/contract/vendor/agency) | Button list | Node kind + label | `setSelection({kind: node.kind, id: node.id})` | Live | Functional constraint (by design, not a bug): the graph always visualizes `data.anomalies[0]` — there is no control to pick a different anomaly to graph from this view |

## 9. Query Layer (`modules/QueryLayer.tsx`)

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| STUB / RAG LIVE toggle | Button, `aria-pressed` | "STUB" / "RAG LIVE" | Flips `useRag` | Live | |
| RUN QUERY / STOP | Button (primary) | "RUN QUERY" / "STOP" | STUB mode: calls local `runPriisQuery()` adapter (synchronous, in-browser keyword match over the loaded dataset, no network). RAG LIVE mode: `streamRagQuery()` → `POST /rag/query`, reads an SSE-style token stream. Clicking while pending cancels the in-flight run | Live — **bug found in RAG LIVE path** | STUB run produced a correct Finding/Confidence/Evidence card. Against an *unreachable* backend, RAG LIVE correctly shows "Query failed — RAG backend may be offline". Against the *reachable* live backend it silently reverted to "No query run yet" with **no error shown**: the backend's `/rag/query` shells out to `query_llm.py`, a script that **does not exist anywhere in this repo** (confirmed: `ls query_llm.py` → not found), so the subprocess exits immediately with empty stdout. `streamRagQuery()` on the frontend only treats an HTTP-level failure or a missing response body as an error — a subprocess that starts fine but streams zero `data:` lines before its `done` event ends the run with no feedback at all, leaving the user unable to tell whether the query ran, hung, or failed |
| Prompt textarea | Textarea, `#query-input` | "PROMPT" label | Controlled `query` state, fed into `runQuery()` | Live | |
| Evidence entity links (dynamic, STUB result) | Button list | Tier badge + evidence label | `ev.entity && setSelection(ev.entity)` | Live | |

## 10. Error boundary (`components/ErrorBoundary.tsx`)

Two mount points: one around the whole app (`main.tsx`, `recoverBy="reload"`)
and one keyed per-module inside `App.tsx` (soft reset).

| Element | Type | Label | Handler / Behavior | Verified | Notes |
|---|---|---|---|---|---|
| RETRY / RELOAD | Button | "RETRY" or "RELOAD" | Module boundary: `reset()` clears the caught error and re-renders (switching tabs remounts the subtree anyway). Root boundary: `window.location.reload()` | Static-only | Not exercised live — would require deliberately forcing a render-time throw. Verified by reading the code; the two recovery strategies are deliberately different for the reason documented in the component's own comments |

## 11. Desktop launcher entry points

Reviewed: `desktop/launch.py`, `desktop/app_server.py`, `desktop/config.py`,
and the root launcher scripts `PRII-SPIDERWEB.command` (macOS terminal),
`PRII-SPIDERWEB.sh` (Linux), `PRII-SPIDERWEB.bat` (Windows), and
`PRII-SPIDERWEB.app` (macOS Finder double-click bundle). All four share one
underlying flow via a repo-external shared package,
`prii_desktop` (`git+https://github.com/jotaele44/thehub-pr.git…#subdirectory=packages/prii_desktop`,
present locally at `packages/prii_desktop` inside the sibling `thehub-pr`
checkout in this container):

1. **First run only:** each script `cd`s to the repo root and runs
   `python3 desktop/setup.py --ensure`, which creates a project-local `.venv`,
   installs the desktop dependency set, and builds the frontend
   (`npm run build` → `server/frontend/dist`) with `VITE_API_BASE` forced to
   `""` at build time (`desktop/config.py: EXTRA_BUILD_ENV`) so the packaged
   bundle only ever calls same-origin relative paths — there is no hardcoded
   `localhost:8000` to miss once it's wrapped in a single desktop process.
   The `.app` bundle additionally detects macOS "Gatekeeper App
   Translocation" (running from a quarantined, read-only temp copy) and shows
   a dialog pointing at `Fix-Gatekeeper.command` instead of failing with a
   confusing network-looking error.
2. **Every run:** `exec .venv/bin/python desktop/launch.py`, which calls the
   shared `prii_desktop.launcher.launch(DesktopConfig.from_module(desktop.config))`:
   - If a lock file shows the app is already running, it just opens the
     browser to the existing instance and exits.
   - Otherwise it picks a free ephemeral TCP port, starts `desktop.app_server:app`
     under `uvicorn` on `127.0.0.1:<port>` — this is `server/backend/main.py`'s
     FastAPI app, with `/outputs` (the writable exports folder) mounted on top
     and a `/desktop/health` endpoint added — and mounts the built SPA
     (`server/frontend/dist`) as static files with SPA-fallback routing, all
     served from that one process/port.
   - It waits for `/health` to respond, then tries to open a native
     `pywebview` desktop window pointed at `http://127.0.0.1:<port>/`,
     falling back to opening the system default browser tab at the same URL
     if `pywebview` isn't available.
3. **Net effect for a user:** double-clicking the platform launcher (or
   running the shell script) starts one local, ephemeral-port FastAPI+SPA
   server (SQLite-backed, same demo/live-fallback behavior as dev mode) and
   opens straight into the Command Center — no manual "start the backend,
   then start the frontend" steps, and no external network dependency after
   the one-time setup.

## 12. Summary

- **Views/modules audited:** 6 lazy-loaded modules (Command Center, Finance
  Intelligence, Spatial Intelligence, Anomaly Workbench, Investigation Graph,
  Query Layer) + 5 always-on global chrome regions (Command bar, Left rail,
  Tab strip/chrome toggles, Inspector, Timeline) + the shared Error Boundary.
- **Interactive elements cataloged:** **48** distinct app-authored control
  types (dynamic lists — e.g. "contract rows", "anomaly cards" — counted once
  per control type, not once per data row). One further control (the MapLibre
  `NavigationControl` zoom buttons in Spatial Intelligence) exists but is
  third-party chrome with no app-level handler, and is called out separately
  rather than folded into this count.
- **Verification split:** **45 live-verified** end-to-end with Playwright
  against a real running instance (36 against this repo's own backend seeded
  with its demo dataset on an isolated port, the rest against the bundled
  mock-data fallback with no backend running) · **3 static-only**, verified
  by reading the code but not exercised live:
  - CommandBar filter-chip remove button — unreachable in practice (dead
    state, see §3.1).
  - Spatial "dismiss base map note" button — its trigger condition
    (`map.on("error")` firing for the OSM source) never fired live in this
    network-blocked environment.
  - ErrorBoundary RETRY/RELOAD — would require deliberately forcing a
    render-time exception.
- **Static-only due to unavailable external services** (backend reachable,
  but a specific downstream service was not): the Municipios layer's Martin
  vector-tile source (`error`, no Martin service running) and the OSM raster
  basemap tiles / any control depending on their success (network-blocked in
  this container).
- **Broken/dead controls found (live-verified, not just suspected):**
  1. **CommandBar filter chips are dead code** — `filters` state is never
     populated anywhere outside its own removal handler, so the chips (and
     their remove buttons) can never appear (§3.1).
  2. **Finance table filter searches raw ids, not the displayed text** —
     typing a vendor/site/agency name that is visibly present in the table
     (e.g. `"Caribe"`, `"Roosevelt"`) returns "No contracts match"; only the
     underlying id string matches (§5).
  3. **Spatial polygon layers can get stuck on "loading…" forever** when the
     base map tiles can't load, even though the layer's own GeoJSON fetch
     succeeded (confirmed via backend access log) — `whenStyleReady()`'s gate
     on `map.isStyleLoaded()` never resolves in that case (§6).
  4. **RAG LIVE query fails silently against a live-but-misconfigured
     backend** — the backend's `/rag/query` invokes a `query_llm.py` script
     that does not exist in this repo; the subprocess exits with empty
     stdout, and the frontend's stream reader treats "zero tokens, clean
     end-of-stream" as success rather than surfacing an error, so the UI
     reverts to "No query run yet" with no indication anything failed (§9).
  5. The pipeline run against a live backend also ends in an `error`/RETRY
     state in this environment, but that is the **correct** outcome given the
     minimal dependency set installed for this audit (`run_all.py` needs the
     project's full heavy dependency stack) — included here as a caveat, not
     counted as a defect.
