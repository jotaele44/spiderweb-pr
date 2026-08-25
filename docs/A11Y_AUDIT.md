# Accessibility Audit — Spiderweb (PRII)

_Audited 2026-08-24 against the tip of `main`, on branch
`claude/a11y-design-audit-spiderweb-pr-6b85f9`. Follows up on the GUI/controls
audit in `docs/GUI_AUDIT.md` (2026-08-23) with an accessibility pass and the
design-system-usage data collected in `docs/design-system-usage.json`._

## 1. Overview

Spiderweb's GUI (`server/frontend`) is a single-page React app with no
component library and no shared design package: every control is hand-written
CSS on top of a `--fd-*` token system (`styles/federation.css`,
`styles/app.css`). See `docs/design-system-usage.json` for the full
control-by-control source map. Navigation between the app's six modules
(Command, Finance, Spatial, Anomaly, Graph, Query) is in-app React state
(`moduleId`), not URL routing — there is one route, and no `<dialog>` /
modal component anywhere in the codebase.

The repo already carries **one piece of automated a11y coverage**:
`server/frontend/src/a11y.test.tsx`, a Vitest/jsdom suite that runs raw
`axe-core` against eight of the app's components/modules in isolation. Re-run
during this audit, it currently passes clean: **9/9 tests passing**. Its own
comments are explicit about its scope, and this live pass was designed to
cover exactly the gaps it names:

- Scoped to `moderate`-or-worse impact; `color-contrast` is **explicitly
  disabled** because jsdom doesn't compute layout or resolve CSS custom
  properties.
- **`SpatialIntelligence` is excluded entirely** — it constructs a MapLibre GL
  map on mount, which needs WebGL and isn't available in jsdom.
- It renders components directly with hand-built props/mock data — it never
  exercises real keyboard-focus behavior, real viewport sizing, or the actual
  running app shell (`App.tsx`'s 3-column grid, tab strip, timeline).

This audit's live, browser-driven pass is the complement to that: real
Chromium, real viewports, real keyboard `Tab` presses, and — critically —
`SpatialIntelligence` and color-contrast, the two things the jsdom suite
cannot check.

## 2. Method

**Scope, stated explicitly as a subset:** four of the app's six
module-states — the primary route (default state, Command Center) plus
Finance Intelligence, Spatial Intelligence, and Anomaly Workbench, reached by
in-app tab clicks (Graph and Query were not scanned; see §5 Scope
limitations) — each at two viewports (390×844 "mobile," 1280×800 "desktop"),
against one interaction state (default module data, no drill-down selection
except for the panel screenshot). Backend live-data mode was **not**
exercised end-to-end (see below); the app's own offline/demo fallback was in
effect throughout.

**Servers:** backend (`server/backend/main.py`) started on port 8103
(`uvicorn server.backend.main:app --port 8103`, against the already-seeded
`server/priis.db`); frontend on port 5303
(`VITE_API_BASE=http://127.0.0.1:8103 npx vite --port 5303`). Per the handoff
instructions, `VITE_API_BASE` was tried first, in preference to patching the
backend's CORS allow-list. **`server/backend/main.py` was left untouched —
no CORS patch was applied at all**, for a specific reason found during setup:
setting `VITE_API_BASE` correctly repoints the fetch target, but the backend's
CORS allow-list (`allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]`)
doesn't include origin `5303` regardless of where those requests are aimed —
confirmed live: the browser blocked every `/agencies`, `/contracts`,
`/anomalies`, etc. request with "No 'Access-Control-Allow-Origin' header is
present." Rather than patch CORS for a one-off local run, this audit relied on
the app's own designed-in resilience: `fetchPriisDataWithFallback()`
(`src/api/client.ts`) catches exactly this failure and falls back to the
bundled mock dataset, and the header visibly read `DEMO · STANDBY` throughout
every screenshot. The UI is fully interactive and representative either way —
module switching, badges, panels, and layout are driven by the same
components and the same (fixture) data shape in both modes — so this was
judged sufficient for an a11y/design-system pass and avoided leaving a
main.py diff to revert. If a future audit specifically needs to verify
*live*-mode-only behavior (e.g. the RAG-query or pipeline-run paths already
covered in `GUI_AUDIT.md`), CORS will need a real patch (added + reverted, or
made permanent via a repo decision) — noted here rather than done
speculatively.

**Tooling:** the shared `/home/user/.a11y-runner` (pinned Playwright 1.62.1 +
`@axe-core/playwright` against axe-core 4.12.1, explicit Chromium
`executablePath`, its hydration-race fix already in place — `networkidle` +
800ms settle before every check). Its own `tests/federation-smoke.spec.js` is
route-based and can't reach Spiderweb's in-app module tabs, so a throwaway
script (written into that directory per the handoff's own suggested pattern,
reusing its installed Playwright/axe-core packages, and deleted again before
finishing — not committed anywhere) drove: `axe-core` (critical/serious
violations only), a keyboard first-`Tab`-focus-visible check, a horizontal
-overflow check, and a touch-target-size (≥44px height) check, against each
of the four module states at both viewports, plus screenshot capture for
`docs/design-system-usage.json`.

One correctness issue surfaced and was fixed mid-run, worth recording because
it's itself a finding (§4.3): at the mobile viewport, `page.click()` on a
module tab intercepted-and-failed because an overlapping panel sits on top of
the tab strip; even `{force: true}` — which bypasses Playwright's own
actionability checks but still dispatches a real, hit-tested OS-level click —
landed on the intercepting panel instead, silently leaving the module
unchanged. Every tab switch was re-verified by checking `aria-selected` on
the target tab afterward, and calls that didn't switch state successfully
were retried via `dispatchEvent('click')` (which invokes the tab's `onClick`
handler directly, bypassing hit-testing) until confirmed. All results below
are from **state-confirmed** module views.

## 3. Results by module × viewport

Legend: **Axe** = critical/serious `axe-core` violations found. **Focus** =
computed `outline-style` on the element that received the very first `Tab`
press after page load (fresh per module state). **Overflow** = does
`document.documentElement.scrollWidth > clientWidth`. **Touch** = count of
visible `<button>` elements under 44px tall, out of total visible buttons.

| Module | Viewport | Axe (crit/serious) | Overflow | Touch targets <44px | First-Tab focus visible |
|---|---|---|---|---|---|
| Command Center (primary route) | 390×844 | none | **yes** | 39 / 39 | **no** (query input, `outline: none`) |
| Command Center (primary route) | 1280×800 | none | no | 39 / 39 | **no** (same query input) |
| Finance Intelligence | 390×844 | none | **yes** | 48 / 48 | yes (`.navbtn`, solid 2px) |
| Finance Intelligence | 1280×800 | none | no | 48 / 48 | yes (`.tab`, solid 2px) |
| Spatial Intelligence | 390×844 | none | **yes** | 61 / 61 | yes (`.timeline-track`, solid 2px) |
| Spatial Intelligence | 1280×800 | **1: `color-contrast` (serious)** | no | 61 / 61 | yes (`.tab`, solid 2px) |
| Anomaly Workbench | 390×844 | none | **yes** | 41 / 41 | yes (`.timeline-track`, solid 2px) |
| Anomaly Workbench | 1280×800 | none | no | 41 / 41 | yes (`.tab`, solid 2px) |

The "41/61 out of 41/61" touch-target lines mean *every* visible button on
that screen is under the 44px target — see §4.2 for why that reading needs
context, not blind alarm.

## 4. Findings

### 4.1 No visible keyboard focus indicator on the global query input (serious)

The very first thing a keyboard user's `Tab` press lands on, on every load of
every module, is the global command-bar query input
(`components/CommandBar.tsx:53`, `aria-label="Global Spiderweb query"`) — and
it renders with **no focus ring at all** (`outline-style: none`,
`outline-width: 0px`, `box-shadow: none`, confirmed live at both viewports).

Root cause, read from source: `styles/app.css:89`

```css
.query input { flex: 1; border: 0; outline: none; background: transparent; color: var(--ink); }
```

`styles/federation.css:90-93` defines a global, app-wide focus-visible ring —

```css
:where(button, a, input, select, textarea, [tabindex]):focus-visible {
  outline: 2px solid var(--fd-accent);
  outline-offset: 2px;
}
```

— and every other focusable element in the app correctly shows it (confirmed:
`.navbtn`, `.tab`, and `.timeline-track` all showed a solid 2px outline on
first-Tab in the table above). But `.query input`'s own `outline: none` is a
more specific selector and unconditionally wins, silently opting this one
input out of the app's own focus-visible system. A sighted keyboard-only user
tabbing into the app has no way to tell they've landed in the query field.
This is a **WCAG 2.1 §2.4.7 (Focus Visible)** violation, not caught by the
axe pass (axe's DOM-static analysis doesn't evaluate `:focus-visible` state)
or by the existing jsdom suite (which doesn't drive real keyboard focus at
all) — exactly the kind of gap this live pass exists to catch.

**Fix sketch:** drop `outline: none` from `.query input` (or replace it with
an input-appropriate focus treatment, e.g. a border/background change plus
keeping the outline) so it inherits the global focus-visible rule like every
other control.

### 4.2 Spatial "error"-status layer badge fails color contrast (serious, axe-flagged)

`axe-core` flagged `button[data-status="error"] > span:nth-child(2)` (the
Municipios layer toggle, in its error state — see `GUI_AUDIT.md` §6 for why
it errors: no Martin tile service running here) as a `color-contrast`
violation. Traced and measured directly (`getComputedStyle` in a live page,
light theme, the default in this environment):

- Text color: `rgb(168, 58, 28)` (`--fd-alert` / `--alert`, the light-theme
  alert red)
- Background: `rgb(20, 24, 28)` (`--fd-surface` → `--ink`, the app's near-black
  "active" background)
- **Computed contrast ratio: ≈2.79:1** — well under the 4.5:1 AA minimum for
  normal text (and under even the 3:1 AA-large threshold).

Root cause: `styles/app.css:101` sets `.navbtn[data-active="true"] { background: var(--ink); color: var(--surface-2); }`
(dark background, light text) for any *active* nav-button — but
`styles/app.css:205`'s status-color override, `.navbtn[data-status="error"] > span:last-child { color: var(--alert) }`,
always applies the **light-theme** alert red regardless of whether the button
is currently in that dark "active" background state. `--alert` (`#a83a1c`)
was chosen and contrast-checked (per the token file's own comments) against
the *light* `--surface` background (`#f8f6f0`, ≈5.9:1 — genuinely fine there)
but nobody checked it against the *active/dark* `--ink` background the same
button can render on. This is a real, reproducible **WCAG 1.4.3 (Contrast
Minimum)** failure, live-confirmed, not a false positive.

**Fix sketch:** give the error-status span a color that's contrast-checked
against both the resting (`--surface`) and active (`--ink`) backgrounds a
`.navbtn` can have — e.g. switch to `--surface-2`-on-`--ink` for the active
case, or use a status pill/border instead of overloading the button's own
text color.

### 4.3 Mobile viewport (390×844): fixed 3-column layout doesn't collapse (serious, responsive)

At the 390px-wide viewport, **every** module showed `document.documentElement.scrollWidth > clientWidth`
(horizontal overflow), and — more seriously than the overflow number alone
suggests — the persistent 3-column grid (left rail / workspace / right
Inspector, per `GUI_AUDIT.md` §1) does not reflow or collapse at this width.
The Inspector panel visually overlaps the tab strip and other chrome; a
regular `page.click()` on a module tab timed out because the Inspector's own
elements ("intercepts pointer events," in Playwright's own diagnostic)
sat on top of it, and this reproduced consistently, not as a one-off race.
See `docs/a11y-evidence/control-buttons-mobile-390x844.png` and
`badges-mobile-390x844.png` — the header text visibly overlaps
("Spiderweb" / "INTEGRATED INTELLIGENCE..." collide) and the workspace
column's content (badges, cards) is pushed off-screen to the right of the
390px viewport entirely, reachable only by horizontal scrolling nobody is
cued to do.

This is a **WCAG 1.4.10 (Reflow)**-adjacent finding (the reflow criterion's
own reference width, 320 CSS px, is narrower still than the 390px tested
here, so this environment fails a *less* strict width than the spec's own
bar) and, independently, a real interaction defect: a real mobile user
tapping where a module tab visually appears may hit the Inspector panel
instead, with no visual cue why nothing happened.

**Fix sketch:** the 3-column grid needs a real mobile breakpoint — collapsing
the rail and Inspector into off-canvas drawers (both already have collapse
state/`localStorage` persistence and `«`/`»` toggle buttons — GUI_AUDIT.md
§3.2/3.3/3.4 — so the mechanism exists, it's just not wired to trigger
automatically below a width threshold, and even collapsed, the grid template
itself would need a mobile-specific column layout).

### 4.4 Touch targets under 44px — real, but mostly by design intent (informational, not newly actionable)

Every module showed dozens of `<button>` elements under the 44px
minimum-touch-target guideline (WCAG 2.5.5 / Level AAA, and a common
mobile-usability baseline even where not a hard AA requirement) — see the
table in §3. Reading the actual failure lists (full detail in
`/home/user/.a11y-runner`'s run output, summarized here): the overwhelming
majority are the left-rail's dense, deliberately compact list rows (source
rows, watchlist rows, timeline event-marker chips, table column-sort
headers, table data-rows) — a workbench-density UI choice consistent with
this being an "operator console," not a touch-first app (see
`GUI_AUDIT.md`'s own framing throughout). Two exceptions stand out as
closer to real touch targets worth a second look: the theme toggle ("◑
DARK", 40×46 at mobile / 27×56 at desktop) and RUN PIPELINE (40×72 /
27×92) — both primary, deliberately-tappable command-bar actions, both under
44px tall at *both* viewports including mobile. Flagging these two
specifically rather than the whole 39-88-item list, since treating every
dense list row as an equally-weighted defect would bury the two that most
plausibly warrant a real fix.

### 4.5 Spatial Intelligence unlabeled icon buttons (touch-target scan side-finding)

The touch-target scan on Spatial Intelligence surfaced roughly a dozen
buttons with **empty innerText** (`"label": ""`) at both viewports — these
are icon-only layer-panel controls (collapse/expand, per-layer icon buttons)
that render no accessible text content the scan's `innerText` probe could
read. Axe itself didn't flag these as violations (they may carry
`aria-label`s not surfaced by `innerText`), but it's worth a manual pass to
confirm every icon-only control here has a real accessible name — the scan
couldn't fully rule that in or out from the outside.

## 5. Scope limitations

- **Two of six modules not scanned live:** Investigation Graph and Query
  Layer were not included in this pass (the task scope was "primary route +
  up to 4 of the 6 modules"; Command Center, Finance, Spatial, and Anomaly
  were chosen as the candidates named in the handoff). Both are covered by
  the jsdom suite (`src/a11y.test.tsx`) at `moderate`-or-worse impact,
  color-contrast excluded — so they have *some* coverage, just not this
  pass's live/keyboard/contrast/viewport checks.
- **One interaction state per module:** each module was scanned in its
  default/no-selection state (plus one drill-down — an anomaly-card click —
  for the Inspector-panel screenshot only). Deeper interaction states (an
  open Finance-table row, an active pipeline run, a populated RAG-query
  result, a toggled-on Spatial polygon layer actually rendering) were not
  separately a11y-scanned; `GUI_AUDIT.md` covers their *functional* behavior
  in depth, this audit adds nothing new there.
- **Live backend data mode not exercised end-to-end.** As explained in §2,
  CORS blocked the frontend's cross-origin fetches to the port-8103 backend
  throughout, so every scan ran against the app's bundled mock/demo dataset
  (`DEMO · STANDBY`), not live SQLite-backed data. Since the same components
  render either data source through the same code paths, this is judged not
  to materially affect the a11y/design-system findings above — but it does
  mean no assessment was made of, e.g., how the UI behaves with the
  much-larger record counts a real live dataset might have (virtualization,
  table-density, or pagination-related a11y concerns are out of scope here).
- **Only two fixed viewports** (390×844, 1280×800) were tested, per the
  task's required set — no tablet-width or ultra-wide breakpoints, and no
  test of intermediate widths between the mobile-overflow point (§4.3) and
  the desktop layout's onset.
- **Screen-reader software was not run.** All checks are `axe-core` static
  analysis, computed-style/CSS checks, and programmatic keyboard-focus
  probes — no manual pass with VoiceOver/NVDA/JAWS was performed.
- **Reduced-motion / prefers-contrast media queries were not checked.**
- The one throwaway Playwright script used to drive per-module scans (module
  switching isn't URL-routed, so the shared runner's route-only spec
  couldn't reach it) was written into `/home/user/.a11y-runner` to reuse its
  pinned Playwright/axe-core install, per the handoff's own suggested
  pattern, and **deleted again before finishing this audit** — it was never
  committed to this repo or left behind in that shared directory.
