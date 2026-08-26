# Frontend / GUI audit — `server/frontend`

_Audited 2026-08-01 against `bb85210`. Line references are to that commit unless
a fix landed with this document, in which case the entry says so._

Spiderweb has exactly one interface: the Vite + React + TypeScript SPA at
`server/frontend` (~3.4k LOC of source), served by the `desktop/` wrapper. It
reached its current shape in `fcb658b` (2026-07-29), which deleted two competing
frontends and stripped the flight/airspace surface.

## Scope bar

`README.md` and ADR 0001 mark this SPA **diagnostic-only**: it is a development
and diagnostic tool for this producer, and the supported product surface for the
federation is the hub app (`thehub-pr/server/frontend`). This audit therefore
judges the app as a diagnostic tool. §4 separately costs out what a product-grade
bar would additionally require, so the ADR can be revisited with real numbers
rather than re-litigated informally.

## What is already sound

Worth stating up front, because several repo documents still describe an earlier
state (`docs/MATURITY_AUDIT.md` in particular predates the consolidation and
describes three parallel frontends, 0 tests, and no ESLint):

- CI gates lint, typecheck, test and build (`.github/workflows/ci.yml`, job
  `frontend`). `desktop-build.yml` builds the SPA on all three OSes.
- The design-token split is resolved: `styles/federation.css` holds the canonical
  `--fd-*` layer and `styles/tokens.css` aliases the legacy names onto it.
- Fonts are self-hosted via `@fontsource` (`src/main.tsx`) — no runtime network
  request for typography.
- Theme toggle with `prefers-color-scheme` default and persistence; route
  splitting via `React.lazy`; collapsible chrome with keyboard shortcuts.
- Empty states in every module; `aria-sort` and keyboard-operable rows in the
  contracts table; a keyboard-driven temporal cursor.
- API responses are validated against Zod schemas (`src/schemas/priis.ts`).

Most of `workbench/priis-v1/docs/UI_CLEANUP_PLAN.md` has landed. The remaining
gaps from that plan are Phase 5's automated a11y gate (added here) and Phase 6.3's
bundle-size check (still outstanding — see §5).

---

## 1. Defects

All of the following were verified by reading the code, and all are **fixed in
this change** unless marked otherwise.

### 1.1 Correctness and robustness

| # | Defect | Where |
|---|---|---|
| D1 | No `ErrorBoundary` anywhere — any render throw unmounted the tree and blanked the app. The boundary added by #224 lived in the scaffold deleted by `fcb658b`. | `src/App.tsx`, `src/main.tsx` |
| D2 | `get()` used bare `fetch` with no timeout. A backend that accepted the connection but never answered left `loading: true` forever, so the offline fixture fallback never fired and the UI sat on "Loading PRIIS data…". | `src/api/client.ts` |
| D3 | `startPipeline()` never checked `res.ok`, so a 5xx body was cast straight to `PipelineJob`, yielding `job_id: undefined` and an SSE subscription to `/pipeline/events/undefined`. | `src/api/client.ts` |
| D4 | `streamPipeline()` registered no `onerror`. `EventSource` reconnects silently, so a backend that died mid-run left `runState: "running"` permanently — button stuck on STOP, no way back. | `src/api/client.ts` |
| D5 | `handlePipelineRun` did not catch `startPipeline` rejection: an unhandled promise rejection, with the same stuck-STOP outcome. | `src/App.tsx` |
| D6 | Cancelling a stub query set `pending: false` but the promise still resolved and overwrote the cleared state. `cancelRef` was never cleared on unmount, leaking the RAG stream on tab switch. | `src/modules/QueryLayer.tsx` |
| D7 | `URL.revokeObjectURL` was called synchronously after `.click()` in **four** duplicated copies of the same download helper. Firefox and Safari resolve blob downloads asynchronously, so the revoke can land first and the file arrives empty. | `export/csvExport.ts`, `export/sessionLog.ts`, `export/evidenceBrief.ts`, `modules/InvestigationGraph.tsx` |

D4 is now resolved against `GET /pipeline/status/{job_id}` — a backend route that
already existed and had no caller. A dropped stream is not a dead job, though:
the subprocess in `pipeline_run` keeps going, so abandoning the stream would
strand a job the operator can neither stop nor monitor while the UI offered to
start a second one. `streamPipeline` therefore takes over with status polling and
keeps reporting "running" until the job actually reaches a terminal state,
returning a handle whose `close()` tears down both the socket and the polling.
For the same reason a failed `DELETE /pipeline/{job_id}` now keeps the job id and
stays in "running" rather than resetting the button.

The `ErrorBoundary` distinguishes the two places it is mounted. Inside the
workbench it offers RETRY, which is meaningful because the boundary is keyed on
the module and switching tabs remounts the subtree. At the root it offers RELOAD:
a soft reset there re-renders the same children with the same props, so a
deterministic render error would land straight back on a fallback that has
replaced all navigation.

### 1.1b The live path was broken, and failed silently

Found by running the app against a seeded backend rather than by reading it —
neither defect is visible in the source, and neither had a test.

**D8 — the demo seed and the frontend schema spoke different vocabularies.**
`src/schemas/priis.ts` validates every response with Zod, and `parseArray` drops
non-conforming rows **silently** (it warns only under `import.meta.env.DEV`).
`server/ingestion/seed_demo.py` had drifted onto its own vocabulary, so in live
mode the frontend discarded almost everything while the header still read LIVE:

| Endpoint | Field | Seed emitted | Frontend accepts |
|---|---|---|---|
| `/contracts` | `status` | `active`, `review` | `planned`/`executed`/`amended`/`flagged`/`closed`/`unknown` |
| `/contracts` | `procurement_method` | `open`, `restricted`, `sole-source` | `competitive`/`sole_source`/`emergency`/`amendment`/`unknown` |
| `/anomalies` | `category` | `misc`, `procurement` | `financial`/`spatial`/`temporal`/`infrastructure`/`imagery`/`report`/`cross-domain` |
| `/anomalies` | `band` | `high`, `medium`, `low` | `lo`/`md`/`hi` |
| `/sources` | `kind` | `adsb`, `filings`, `imagery`, `osint`, `registry` | `technical`/`operational`/`eyewitness`/`secondary`/`derived` |
| `/sources` | `status` | `degraded` | `online`/`partial`/`offline` |
| `/alerts` | `kind` | `filing` | `finance`/`spatial`/`source`/`anomaly`/`report` |

The observable symptom was Finance rendering "No contracts in the current
dataset" against a backend that had just served seven of them. Because the
fallback triggers on a thrown error and not on an empty result, the app stayed in
LIVE mode and reported nothing wrong.

The frontend enums are canonical — `server/ingestion/ingest_data.py`, the real
ingest path, already defaults to `cross-domain`, `md` and `unknown`. The seed was
corrected. The `adsb` source kind was also a leftover of the airspace surface
`fcb658b` retired.

**D9 — the seed stored display names in foreign-key columns.**
`contracts.agency` held `"Demo Agency Alpha"` and `contracts.vendor` held
`"Demo Vendor A"`, while `/agencies` and `/vendors` key on `DEMO-AG-1` /
`DEMO-VN-A`. The UI resolves these with `byId()`, so the contract pane's
"Agency ·" and "Vendor ·" buttons simply did not render — a link that vanishes
rather than errors. `contracts.site` was already an id, which is why site links
worked and the inconsistency went unnoticed.

Both are now pinned by `tests/test_seed_demo_contract.py`, which checks every
seeded enum against the frontend vocabulary and asserts every foreign key
resolves. The enums are duplicated in that test on purpose: it is a
cross-language boundary, and the test exists to fail when the two sides drift.

The general risk remains and is **not** fixed: `parseArray` still drops rows
silently in production builds, so any future backend drift degrades the UI to
"empty" rather than "broken". Surfacing a partial-outage state when validation
drops rows would close that gap.

### 1.2 Navigation dead-ends

`SelectionKind` (`src/types/priis.ts`) declares nine kinds; the Inspector
implemented five. `agency` was reachable from the contract pane
(`Inspector.tsx`, "Agency ·") and from the investigation graph's `agency` node —
both landed on **"Missing record … is not present in the fixture dataset."**

Fixed: `agency`, `source` and `investigation` branches added, and sources and
investigations in the left rail now open the inspector. The `Missing` copy no
longer says "fixture", which was wrong whenever the app was running live.

`finding` remains declared but unreachable and unimplemented — it is only
produced by the query stub's evidence entities, which always carry a concrete
entity kind. Left as-is.

### 1.3 Accessibility

| # | Defect | Where |
|---|---|---|
| A1 | `<h4>` and `<p>` inside a `<button>` — a button's content model is phrasing content only. | `components/AnomalyCard.tsx` |
| A2 | `role="button"` on `<tr>` replaced the implicit `row` role, so cells lost their row ancestor and screen readers lost grid navigation. Now `role="grid"` on the table with `aria-selected` on the row. | `modules/FinanceIntelligence.tsx` |
| A3 | Focusable `<button>`s nested inside a `role="slider"` — unreachable to a screen reader driving the slider. Track and event markers are now stacked siblings. | `components/Timeline.tsx` |
| A4 | Tab strip was bare buttons with no `role="tablist"`/`role="tab"`/`aria-selected`. | `src/App.tsx` |
| A5 | Toggle buttons signalled state only through a `data-active` attribute, invisible to assistive tech. `aria-pressed` added to the layer toggles, layer-panel toggle, RAG/STUB toggle, chrome toggles and investigation rows. | `modules/SpatialIntelligence.tsx`, `modules/QueryLayer.tsx`, `src/App.tsx`, `components/LeftRail.tsx` |
| A6 | Map markers are imperatively created buttons carrying only `title`, leaving them unnamed to assistive tech. `aria-label` added. | `modules/SpatialIntelligence.tsx` |
| A7 | Heading levels jumped `h1` → `h3` in Command Center, Finance and Anomaly Workbench. Section headings promoted to `h2`. | modules and card components |

A7 was found by the new axe gate, not by reading — see §3.

**Note on A2:** axe-core does not flag `role="button"` on `<tr>`; this was
verified empirically by reintroducing the pattern and observing a clean axe run.
It is a genuine ARIA semantics defect, but it is not one an automated gate will
catch, so it is recorded here rather than relied on being caught in future.

### 1.3b Found only by rendering the app

The static and jsdom passes above missed all of the following. They were found by
driving the built app in Chromium against a seeded backend and screenshotting all
six modules in both themes — worth remembering when weighing what a browser gate
is worth here.

**D10 — the app booted onto "Missing record".** The initial state was seeded with
fixture ids (`selection` = anomaly `A-014`, `activeInvestigation` = `INV-007`,
`cursor` = `2024-08-14`, plus three filter chips naming `INV-007`). None resolve
against live data, so a first load showed the Inspector's missing-record pane, the
temporal cursor sat outside the dataset entirely, and the chips referenced an
investigation that did not exist. Initial state is now empty and anchored to
whatever loads — the cursor to the newest event, the investigation to the first
one returned.

**D11 — a stale selection blanked the Anomaly Workbench.** `AnomalyWorkbench`
resolved `selection` to an anomaly or fell through to `undefined`, and its only
guard was for an empty dataset. With D10's `A-014` selected the entire detail
pane rendered nothing — indistinguishable from a broken module. It now falls back
to the head of the cluster queue.

**D12 — WCAG AA contrast failed systematically in both themes.** jsdom cannot
resolve CSS custom properties, so `src/a11y.test.tsx` disables `color-contrast`
and this was entirely uncovered. A real-browser axe run found violations on every
module:

| Element | Was | Cause |
|---|---|---|
| `.tab` (primary nav) | 1.29:1 dark | never set `color`, so it inherited the UA `buttontext` black onto a dark strip |
| `.graph-node` ×10 | 1.29:1 dark | same — a button with no `color` |
| `.brand-sub` | 2.57 / 3.69:1 | `--muted` is tuned for muted-on-surface; `.brand` inverts the background to `--ink` |
| every muted label | 4.47:1 light | `--fd-text-muted` `#6b7280` sat just under 4.5 |
| `.pill[data-tone="warn"]` | 3.18:1 light | `--fd-warn` `#b6802a` |
| `.badge[data-tier="T4"]` | 4.19:1 light | `--fd-t4` `#707070` on `--fd-bg` |
| MapLibre attribution | 2.02:1 both | third-party CSS; links at `rgba(0,0,0,.75)` on black |

All fixed: two missing `color` declarations, four token values re-picked against
computed ratios, a new `--fd-text-on-ink-muted` token for text on an `--ink`
background, and an attribution restyle that underlines links so they are
distinguished without relying on colour. The suite now reports **zero** serious
or moderate WCAG 2 A/AA violations across all six modules in both themes.

**D13 — smaller rendering defects.** The Query Layer's `.query-box` stretched its
two grid rows to full panel height, stranding the PROMPT label at the top and the
textarea at the bottom; it also showed a blank panel before the first run.
Disabled buttons were visually identical to enabled ones (EXPORT BRIEF with no
anomaly selected). Two cards read "fixture"/"fixtures" regardless of live mode —
the same copy defect as the Inspector's "not present in the fixture dataset".

Not reproducible here: the base map renders blank in this sandbox, but zero tile
requests failed, so the proxy is intercepting them rather than the app mishandling
an error. True offline tile behaviour remains untested.

### 1.4 Dead code

- `export/sessionLog.ts` had **zero** importers and no test. Deleted.
- `export/evidenceBrief.ts` was imported only by its own test; `exportAnomaliesCsv`
  was never called. Both are now wired into the Anomaly Workbench as
  EXPORT BRIEF / EXPORT CSV rather than deleted — they were already tested, they
  just had no button.
- `byId` and `fmtMoney` were exported from `data/mockData.ts` and imported by six
  production files, so every module's formatting came from the offline fixture
  module. Moved to `src/lib/format.ts`.
- The `download()` helper existed in four copies. Consolidated into
  `src/export/download.ts`.

---

## 2. Inert controls

Chrome that looks functional, persists across reloads, and drives nothing. **Not
fixed** — each needs a product decision about what "filtered" should mean, and
the diagnostic bar does not obviously require them.

- **Filter chips** (`src/App.tsx`). Rendered in the command bar with a remove
  button each. `filters` is never passed to any module. They can be removed but
  never added, and nothing resets them, so the only reachable states are the
  three seeded chips and subsets of them.
- **Temporal cursor** (`src/App.tsx`, `components/Timeline.tsx`). Persisted to
  `localStorage`, movable by click and by keyboard, displayed in the tab strip —
  and read by no module. Moving it changes nothing but its own label.
- **Active investigation** (`src/App.tsx`, `components/LeftRail.tsx`). Persisted
  and highlighted, but no module scopes to it. `InvestigationGraph` does not even
  receive it as a prop. Selecting an investigation now at least opens it in the
  inspector (§1.2), which is the closest thing to a use it has.

The honest summary: the workbench presents three filtering affordances and
implements none of them. The contracts table's own filter box
(`modules/FinanceIntelligence.tsx`) is the only working filter in the app.

---

## 3. Test coverage

Before this change there were four test files — `api/client`, `schemas/priis`,
`export/csvExport`, `export/evidenceBrief` — and **no test mounted a single one
of the six modules or nine components**.

Added:

- `src/components/ErrorBoundary.test.tsx` — fallback rendering and custom fallback.
- `src/components/Inspector.test.tsx` — the three previously dead-ending kinds
  resolve, and genuinely absent records still report missing.
- `src/api/resilience.test.ts` — timeout aborts, `startPipeline` rejects on non-ok
  and on a missing `job_id`, `getPipelineStatus` reports terminal state.
- `src/a11y.test.tsx` — renders eight components and modules and asserts axe finds
  no moderate-or-worse violations. This is the automated a11y gate
  `UI_CLEANUP_PLAN.md` Phase 5 asked for, run inside `npm run test` (already gated
  by CI) rather than as a separate workflow job.

Plus `tests/test_seed_demo_contract.py` (28 Python tests) pinning the seed/schema
boundary described in §1.1b.

79 frontend tests pass, up from 55.

The suite was also verified end-to-end in Chromium against a seeded backend: LIVE
mode loads real records, the agency and investigation panes resolve instead of
dead-ending, and a pipeline run against an unreachable backend now lands on RETRY
instead of sticking on STOP. Both live-path defects in §1.1b were found this way,
not by reading the code — worth remembering when weighing what a browser-based
gate would be worth here.

Two limits worth stating plainly:

- **`SpatialIntelligence` is not in the a11y gate.** It constructs a MapLibre GL
  map on mount, which needs WebGL; jsdom has none. Covering it needs a real
  browser (Playwright), which this repo does not run for the SPA.
- **Colour contrast is not checked *in CI*.** jsdom does not compute layout or
  resolve CSS custom properties, so the committed gate cannot evaluate it. A
  real-browser scan was run by hand and every violation it found is fixed
  (§1.3b, D12), but nothing stops contrast regressing — promoting that scan to a
  CI gate is the single highest-value follow-up in §5.

---

## 4. Product-grade delta

What would additionally be required if ADR 0001 were revisited and this app had
to be a shippable analyst product rather than a producer diagnostic. None of it
is a defect today — each is documented as intentional in
`workbench/priis-v1/docs/IMPLEMENTATION_HANDOFF.md` and `VECTOR_LOCK.md`.

- **The Query Layer is a hardcoded stub.** `src/adapters/queryAdapter.ts` ignores
  the query text apart from one `"vieques"` keyword, otherwise always returns
  `data.anomalies[0]`, and hardcodes `missingData` and `recommendedAction`. The UI
  bills it as an "LLM orchestration surface". A live RAG path exists behind the
  STUB/RAG LIVE toggle and calls `POST /rag/query`, but the default is the stub.
  Real retrieval means routing to SQL, vector, geospatial, graph and timeline
  tools — the largest single item here.
- **The Investigation Graph is a mockup.** Five nodes at hand-written x/y
  percentages, rendering only `anomalies[0]` and its first contract. No layout
  algorithm, no pan/zoom, no node expansion, and it ignores the active
  investigation. "EXPORT GRAPH" exports the mockup.
- **The Anomaly Workbench is read-only.** No triage: no assign, dismiss, escalate,
  annotate, or status change. The app has no write path for domain data at all:
  the only non-`GET` routes it calls are `POST /pipeline/run`, `POST /rag/query`
  and `DELETE /pipeline/{job_id}`, all of which are job control.
- **No router.** Module selection is `useState`, so there are no deep links, no
  back button, and no shareable view — a significant gap for collaborative work
  and a small change to close (`react-router` or a hash-based scheme).
- **No responsive layout.** `styles/app.css` contains **zero** `@media` queries.
  The shell is a fixed `100vw`/`100vh` three-column grid with hardcoded inline
  column widths (`"1fr 300px"`, `"320px 1fr"`, `"1fr 280px"`). Below roughly
  1100px the centre column is unusable. `index.html` nevertheless ships a mobile
  viewport meta, which sets an expectation the CSS does not meet.
- **No live-data watchlist.** The backend has no watchlist endpoint, so
  `api/client.ts` derives one client-side from high-band anomalies and flagged
  contracts.

---

## 5. Smaller items still open

- **No bundle-size gate** (`UI_CLEANUP_PLAN.md` Phase 6.3). The build currently
  warns: the Spatial chunk is ~1.03 MB raw / ~276 kB gzipped, essentially all
  MapLibre. It is already route-split, so it only loads when the Spatial tab is
  opened, but nothing stops that number growing.
- **Map tiles still need the network.** `TILE_URL` is now configurable via
  `VITE_TILE_URL` (this change) so a packaged build can point at a local source,
  but the default remains `tile.openstreetmap.org`. Fonts were self-hosted during
  the offline hardening; tiles were not. Bundling or caching tiles is the
  remaining offline gap.
- **`/catalog` has no UI.** The backend serves it; nothing in the app calls it.
- **Browser chrome cannot follow the theme toggle.** `index.html` gained a
  description, a `<noscript>` fallback and a web manifest for the previously
  unreferenced `public/icon-512.png`, but its `theme-color` must stay the
  unconditional brand accent: `thehub-pr`'s `tools/build_program_icons.py --check`
  validates it against `assets/branding/icon.png` and `desktop-build.yml` gates on
  it, so `prefers-color-scheme` variants fail the branding check. Making the
  browser chrome theme-aware needs a change in `thehub-pr` first.
- **`dashboard/`** retains two generated PNGs solely to satisfy `thehub-pr`'s
  `build_program_icons.py --check`. Its README records the follow-up (drop the
  `STANDALONE` entry there, then delete the directory) — owned by `thehub-pr`.
- **Copy leaks demo framing into live mode.** Cards read "12m fixture window" and
  "fixtures" regardless of whether the data is live.

## 6. Stale documentation corrected here

- `docs/STATIC_DASHBOARD_MODE.md` documented `scripts/export_static_dashboard.py`
  and `tests/test_static_dashboard_export.py`; **neither existed**. Moved to
  `docs/legacy/` beside the parked script, with a retirement header. It was linked
  from `docs/README.md` as the repo's only UI document.
- `docs/ARCHITECTURE.md` described `dashboard/` as a "Static browser dashboard for
  local review", contradicting `dashboard/README.md`.
- `scripts/priis_smoke.sh` `cd`-ed into `workbench/priis-v1/app`, which no longer
  exists, so its "[4/5] Frontend build" stage could not pass. Repointed at
  `server/frontend`. (The script is not referenced by any workflow.)
