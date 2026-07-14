# PRIIS V1 Workbench — UI Cleanup & Optimization Plan

_Draft. Scope: the interactive workbench app at `workbench/priis-v1/app` (the
Spiderweb producer's diagnostic UI). This plan is advisory — it inventories
concrete issues in the current React/TypeScript + MapLibre app and sequences the
cleanup into reviewable phases. No source was refactored to produce it._

## 1. Scope & context

The repo has three UI surfaces:

| Surface | Path | Role |
|---|---|---|
| **PRIIS V1 workbench** | `workbench/priis-v1/app` | The interactive app — this plan's target |
| Legacy Spiderweb demo | `dashboard/` | CDN React + Babel prototype; locked as the visual reference (`docs/DESIGN_SYSTEM_EXTRACTION.md`) |
| Diagnostic server frontend | `server/frontend` | Producer diagnostic surface (ADR 0001) |

The workbench is a six-module analyst workbench (Command, Finance, Spatial,
Anomaly, Graph, Query) with a global command bar, left rail, right inspector,
and a collapsible-chrome grid. It loads live data from a FastAPI backend and
falls back to a bundled fixture (`data/mockData.ts`) when the backend is down.

The design system is documented and mostly sound (`tokens.css`,
`DESIGN_SYSTEM_EXTRACTION.md`); the problems are **inconsistent application** of
it, a **half-landed second token system**, **dead/unwired UI**, **missing module
states**, and **accessibility gaps** — not the visual direction itself.

## 2. Goals & guardrails

1. **Preserve the locked visual reference.** Cleanup should make the app match
   `DESIGN_SYSTEM_EXTRACTION.md` more faithfully, not restyle it.
2. **One token system, one source of truth.** Resolve the `tokens.css` vs
   `federation.css` split before touching components.
3. **No behavior regressions.** Live/DEMO fallback, selection sync, pipeline
   SSE, and collapsible chrome must keep working.
4. **Ship in small, reviewable phases.** Each phase below is independently
   mergeable and ordered so later phases build on earlier ones.
5. **Accessibility to a baseline.** Keyboard-operable controls, labels on
   inputs, and no color-as-sole-signal.

## 3. Findings summary

### 3.1 Design-system / theming
- **`tokens.css` and `federation.css` are two parallel token systems.**
  `federation.css` (`--fd-*`) is imported in `main.tsx` but **no component
  consumes it** — components use `tokens.css` (`--t1`, `--surface`, `--ink`).
  This is a half-landed Federation Design System pilot (commit #173).
- **Theme is hard-locked to dark.** `main.tsx:9` sets
  `document.documentElement.dataset.theme = "dark"` unconditionally. The full
  light "paper" palette in `tokens.css :root` is dead code, and **there is no
  theme toggle** and no `prefers-color-scheme` handling — even though the CSS
  fully supports both themes.
- **Web fonts load over the network at runtime.** `app.css:2` `@import`s Google
  Fonts (`fonts.googleapis.com`). This blocks first paint and breaks offline —
  a regression against the repo's recent offline hardening (commit #175).

### 3.2 Dead / unwired / hardcoded UI
- **`Timeline` is fully built but never mounted.** `App.tsx` renders no
  `<Timeline>`; the `--time-h` token and a timeline grid row are unused. The
  component also hardcodes its date window (`2024-03-01`..`2025-04-01`,
  `Timeline.tsx:4-5`), which will drift from real data.
- **`InvestigationGraph` is a static scaffold.** It only ever renders
  `anomalies[0]` and its first contract; node coordinates are duplicated between
  the `nodes` array and the hand-written `<svg><line>` coords; **"EXPORT GRAPH"
  has no `onClick`** (dead control).
- **Brittle hardcoded copy in CommandCenter:** `unit=" of 8"` and
  `" ≥0.80"` / `"1 partial source"` are literals that desync from `data`.
- **Duplicated API base URL.** `http://localhost:8000` is hardcoded in both
  `api/client.ts:15` and `SpatialIntelligence.tsx:7`; there is no env config, so
  the app can't point at a non-local backend and will mixed-content-fail on
  HTTPS.

### 3.3 Interactive-workflow gaps
- **Global query is disconnected from the Query module.** The CommandBar query
  (`App.tsx` state) and `QueryLayer`'s own local `query` state are separate;
  submitting the command bar only switches tabs — the typed query is dropped.
- **Missing module states.** `DESIGN_SYSTEM_EXTRACTION.md` requires Empty /
  Loading / Partial-outage / Contradiction / Exportable states per module. In
  practice only App-level loading and the Inspector's null/`Missing` states
  exist. `QueryLayer` and `SpatialIntelligence` have **no error surface** for
  their network calls (RAG stream, tile/GeoJSON fetch fail silently).
- **Robustness.** `InvestigationGraph.tsx:7` and `AnomalyWorkbench.tsx:6` index
  `data.anomalies[0]` with no empty guard (crash / blank on empty data).
- **Live-mode data loss.** `fetchPriisData()` returns `watchlist: []`, so the
  left-rail watchlist silently disappears when the backend is live.

### 3.4 Code-quality: duplication & inline styles
Shared-component opportunities (each duplicated 3–6×):

| Pattern | Duplicated in | Extract to |
|---|---|---|
| KPI `Card` (title/stat/unit/delta) | CommandCenter (local), FinanceIntelligence, AnomalyWorkbench | `components/Card` |
| `AnomalyCard` (`.anom-card[data-band]`) | CommandCenter, SpatialIntelligence, AnomalyWorkbench | `components/AnomalyCard` |
| Entity link list (`.card > h3 + navbtn rows`) | Inspector (×3), AnomalyWorkbench, FinanceIntelligence aside | `components/EntityLinkList` |
| Inspector shell (`aside.inspector > head + body`) | Inspector (×6 branches) | `components/InspectorShell` |
| Rail section (title + button list) | LeftRail (×4) | `components/RailSection` |
| Tone/threshold logic (status/score/risk/band → tone) | ~5 files inline | centralize in `Badges` |

- **Inline styles with magic numbers** instead of classes: FinanceIntelligence
  (filter input, `"1fr 300px"`), SpatialIntelligence (imperative marker styles,
  `Math.sqrt(total/1e6)*5`, resize timeout `320` coupled to a CSS transition),
  AnomalyWorkbench, QueryLayer, Badges, CommandBar.

### 3.5 Accessibility
- **Non-button clickables:** FinanceIntelligence sortable `<th>` and selectable
  `<tr>` (no role/tabindex/keyboard; also missing `aria-sort`); Timeline
  `<footer>` sets the cursor via click math with no keyboard equivalent.
- **Unlabeled inputs:** QueryLayer `<textarea>`, FinanceIntelligence filter
  input (placeholder only).
- **Color-as-sole-signal:** CommandBar sync dot `●` (`CommandBar.tsx:74`)
  conveys status by color only.

## 4. Phased plan

Phases are ordered by dependency and risk. Each is independently mergeable.

### Phase 0 — Foundation: tokens, theme, fonts (S, low risk)
_Do this first; everything else assumes a single token source._
1. **Pick one token system.** Recommended: keep `tokens.css` as the source of
   truth (components already use it), and either (a) map `--fd-*` onto
   `tokens.css` values so `.fd-panel`/focus-ring survive, or (b) remove
   `federation.css` and re-add its two useful rules (`:focus-visible` ring,
   `prefers-reduced-motion`) into `app.css`. Document the decision.
2. **Self-host fonts.** Vendor Public Sans / JetBrains Mono / Source Serif 4
   into the app and drop the runtime `@import`; add `font-display: swap`.
3. **Add a theme toggle.** Small control in the CommandBar; persist to
   `localStorage` (mirror the existing collapse-persistence pattern); default
   from `prefers-color-scheme`. Remove the hard `data-theme="dark"` in
   `main.tsx`. This unlocks the already-built light palette.

_Acceptance:_ app builds and renders identically in dark; toggling switches to
the light paper theme; no network font request; only one `--*`/`--fd-*` system
remains referenced.

### Phase 1 — Config & robustness (S, low risk)
1. **Centralize the API base.** One `config.ts` exporting `API_BASE` from
   `import.meta.env.VITE_API_BASE` (fallback `http://localhost:8000`); consume
   it in `client.ts` and `SpatialIntelligence.tsx`.
2. **Guard empty data.** Null-safe `anomalies[0]` in `InvestigationGraph` and
   `AnomalyWorkbench`; render an empty state instead of crashing/blanking.
3. **Fix live-mode watchlist.** Either fetch a watchlist endpoint or derive it,
   so it doesn't vanish when `live: true`.

_Acceptance:_ app can target a remote backend via env var; empty-fixture load
shows empty states, not errors.

### Phase 2 — Module states (M, low/medium risk)
Add the states the design doc requires, per module:
1. **Loading / empty / error** for `QueryLayer` (RAG + stub failures) and
   `SpatialIntelligence` (tile + GeoJSON fetch failures) — surface a visible
   error card, not a silent no-op.
2. **Empty states** for FinanceIntelligence (zero filtered rows), LeftRail
   sections (empty watchlist/sources), CommandCenter alert feed, and Inspector
   linked-list cards ("none" instead of blank).

_Acceptance:_ each module renders a deliberate state for empty/loading/error;
no blank panels.

### Phase 3 — Shared components & de-duplication (M, medium risk)
Extract the six patterns in §3.4 into `components/`, then replace call sites.
Move all tone/threshold ternaries into `Badges` helpers
(`statusTone`, `scoreTone`, `riskTone`, `bandTone`) so thresholds live in one
place. Sweep inline styles into CSS classes / tokens as each component is
touched.

_Acceptance:_ no duplicated `Card`/`anom-card`/inspector-shell markup; grep for
inline `style={{` drops materially; thresholds defined once.

### Phase 4 — Interactive workflow (M, medium risk)
1. **Wire the global query into the Query module.** Lift query state (or pass it
   on `onSubmit`) so submitting the CommandBar populates and runs `QueryLayer`;
   remove `QueryLayer`'s redundant second "Execute" button.
2. **Mount the Timeline** (or explicitly remove it). If mounting: add the
   timeline grid row (`--time-h`), drive its window from data instead of the
   hardcoded dates, and make cursor changes sync selection. If removing: delete
   the component and `--time-h` and note it in the design doc.
3. **Make `InvestigationGraph` data-driven** or clearly mark it a scaffold: at
   minimum wire "EXPORT GRAPH" (or remove it) and derive node positions once so
   the SVG and node array share one source.

_Acceptance:_ typing a query in the command bar and hitting Enter runs it in the
Query module; no dead controls remain.

### Phase 5 — Accessibility pass (S/M, low risk)
1. Make sortable `<th>` real buttons with `aria-sort`; make selectable table
   rows keyboard-operable (row-level button or `role="row"` + key handling).
2. Add `aria-label`/`<label>` to the QueryLayer textarea and Finance filter.
3. Give the Timeline (if kept) a keyboard cursor control.
4. Pair the CommandBar sync dot with text (`SYNC OK` / `DEGRADED`), not color
   alone. Add a visible focus ring globally (already in `federation.css` —
   preserve it in Phase 0).

_Acceptance:_ keyboard-only walkthrough of every module reaches all controls;
axe/Lighthouse a11y has no critical violations.

### Phase 6 — Performance & optimization (S, low risk)
1. **Route-split modules** with `React.lazy` (MapLibre + TanStack Table are
   heavy; Spatial and Finance shouldn't load until selected).
2. **Memoize** derived aggregates (`vendorTotals`, contract totals recomputed on
   every render) and stabilize marker rebuilds in Spatial.
3. **Verify the production bundle** (self-hosted fonts, tree-shaken maplibre) and
   add a rough bundle-size check to CI.

_Acceptance:_ initial JS payload drops (map/table code lazy-loaded); no
avoidable recompute on re-render.

## 5. Sequencing & effort

```
Phase 0 (tokens/theme/fonts) ─┬─> Phase 3 (shared components)
Phase 1 (config/robustness) ──┤
Phase 2 (module states) ──────┴─> Phase 4 (workflow) ─> Phase 5 (a11y) ─> Phase 6 (perf)
```

| Phase | Effort | Risk | Blocks |
|---|---|---|---|
| 0 Tokens/theme/fonts | S | Low | 3 |
| 1 Config/robustness | S | Low | — |
| 2 Module states | M | Low/Med | — |
| 3 Shared components | M | Med | 4 |
| 4 Workflow | M | Med | 5 |
| 5 Accessibility | S/M | Low | — |
| 6 Performance | S | Low | — |

**Quick wins (do first):** Phase 0 self-host fonts + theme toggle, Phase 1 API
base env var, Phase 4 "EXPORT GRAPH" dead-control fix.

## 6. Out of scope / open decisions

- **Timeline: mount or delete?** It's a documented part of the workbench
  geometry but currently unmounted. Needs a product call (Phase 4).
- **Which token system wins** (`tokens.css` vs `federation.css`) is a design-
  system-governance decision that should be made explicitly, not by drift.
- Backend contract changes (e.g. a real watchlist/graph endpoint) are owned by
  the FastAPI server, not this app.
- The legacy `dashboard/` prototype and `server/frontend` are separate surfaces
  and out of scope here.
