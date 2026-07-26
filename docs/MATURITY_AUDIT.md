# spiderweb-pr — Professional Maturity Audit

**Date:** 2026-07-26 · **Method:** static review **plus execution** — every number below came
from running the code in a clean container (Python 3.11.15, Node v22.22.2). Setup and test
invocation followed `.github/workflows/ci.yml`
(`uv pip install --system -e ".[airspace,earthgpt,server,dev]" "httpx>=0.27"`).

Scope: this repository only. Cross-repo comparisons live in
[`thehub-pr/docs/FEDERATION_MATURITY_AUDIT.md`](https://github.com/jotaele44/thehub-pr/blob/main/docs/FEDERATION_MATURITY_AUDIT.md).

---

## Scorecard

| Dim | Area | Score | Evidence |
|---|---|---|---|
| D1 | Functional completeness | **4** | 53.8k LOC; SSE streaming, GeoJSON layer service, RAG, contract-finance scoring — all real and serving |
| D2 | Data reality | **3** | Declares `PRODUCTION` with hub-validated first real package (1 site observation + 9 airport reference locations); modest but genuine |
| D3 | UI craft | **0** | **Three parallel frontends, none complete.** The TypeScript one has 0 pages, 483 LOC, 3 `aria-*`, 0 loading states, 0 empty states, 0 `ErrorBoundary`, and no ESLint config. |
| D4 | Test coverage | **4** | **`989 passed, 31 skipped`** in 33.0s; 86 test files, 13.9k LOC of tests; CI enforces `--cov-fail-under=62` |
| D5 | Engineering hygiene | **2** | ruff+black+mypy are configured and clean — but CI runs them against a **13-file allowlist out of 311 Python files (4%)** |
| D6 | Doc accuracy | **4** | 83 markdown files; `federation.json` accurately describes the module set and provenance |

**Overall: a serious backend with a quality gate that covers 4% of it and a frontend that
barely exists.** The test suite is genuinely strong — 989 tests with a 62% coverage floor.
The lint story is the opposite: an allowlist that has not grown with the codebase.

---

## The lint allowlist

`.github/workflows/ci.yml:70` pins the checked set explicitly:

```
LINT_PATHS="provenance_utils.py run_modes.py integration/mbil.py pipeline/db_utils.py
pipeline/terrain_hook.py federation/envelope.py federation/readiness.py
federation/namespace.py pipeline/logging_config.py pipeline/config_loader.py
pipeline/seeding.py pipeline/verbosity.py pipeline/path_safety.py"
```

13 files. The repo has 311. Verified: `ruff check $LINT_PATHS` → **All checks passed**;
`ruff check .` → **1,870 findings**. CI is honestly green and the codebase is 96% unchecked.
An allowlist is a reasonable way to start on a large legacy surface; the failure mode is
never extending it, and that is what happened here.

---

## What is fully developed vs. what is not

**PRODUCTION**

| Module | Evidence |
|---|---|
| `pipeline/` (18 files, 5,526 LOC) | normalization, seeding, config loading, path safety, terrain hook; the best-tested and only substantially lint-gated area |
| `server/backend/main.py` (456 LOC) | 23 routes — `/agencies`, `/vendors`, `/sites`, `/contracts`, `/events`, `/anomalies`, plus SSE streaming and GeoJSON layer endpoints |
| `readiness/contract_finance_layer.py` (2,761 LOC in `readiness/`) | scores MoneySweep's contract-finance bundle into `contract_finance_scored_overlay.geojson`, surfacing Centinelas provenance |
| `federation/` | `envelope.py`, `readiness.py`, `namespace.py` — all inside the lint allowlist and mypy-checked |
| `integration/mbil.py` (1,900 LOC in `integration/`) | lint- and type-gated |
| Test suite | 86 files, 13,859 LOC, `--cov-fail-under=62` enforced in CI |

**FUNCTIONAL**

| Module | Gap |
|---|---|
| `earthgpt/` (24 files, 1,586 LOC) | RAG layer; behind an optional extra, outside the lint allowlist |
| `imagery/` (14 files, 1,259 LOC), `tools/` (9 files, 4,054 LOC) | working, entirely unlinted |
| `scripts/` (70 files, 11,987 LOC) | more than twice the LOC of the `spiderweb/` package (1,592) |

**SCAFFOLD**

| Item | Why |
|---|---|
| `server/frontend/` | 10 source files, 483 LOC, **0 pages**. `App.tsx` + three panes (`MapPane`, `FinancePane`, `LayerCatalogPane`). No router, no ESLint config, no `lint` script. |
| `dashboard/` | a separate vanilla-JSX app (`dashboard.jsx`, `dashboard_contract_finance.jsx`, `dashboard_temporal_waves.jsx`) with vendored libraries |
| `workbench/priis-v1/app/` | a third Vite app with its own `package.json`, `eslint.config.js`, and tsconfigs |

**DEAD** — none found. This repo ships no auth UI and no fake login. Its 4 mutating backend
routes are domain-specific rather than a generic entity store, so the unauthenticated-write
issue affecting `thehub-pr` and `skywatcher-pr` does not apply here in the same form.

---

## UI feature matrix

| Frontend | Pages | LOC | Lint | Tests | Verdict |
|---|---|---|---|---|---|
| `server/frontend/` (TypeScript, Vite) | 0 | 483 | **no config, no script** | 0 | **Scaffold** — builds, renders three panes, no routing |
| `dashboard/` (vanilla JSX + vendored libs) | n/a | — | — | 0 | **Parallel legacy** |
| `workbench/priis-v1/app/` (Vite + TS) | — | — | own eslint config | 0 | **Third parallel app** |

`server/frontend/src/lib/api.ts` is the one well-built piece: `API_BASE` indirection,
`AbortSignal.timeout(8000)`, and a populated 28 KB `snapshot.json` covering `/health`,
`/sites`, `/contracts`, `/events`, `/anomalies`, `/sources`, `/catalog` for offline export
builds. The client is ready; there is no application on top of it.

Three frontends, zero pages, zero tests, one missing lint config — for the second-largest
backend in the federation.

---

## No fixes applied in this PR

The federation-wide fixes in this audit round (gating dead auth routes, guarding
unauthenticated entity writes) do not apply here: this repo ships no auth UI and no generic
`/api/entities` store. Its documentation drift check came back clean.

This PR therefore adds the audit document only. That is the honest outcome — the significant
work here (consolidating three frontends, extending the lint allowlist) is scoped change that
deserves its own review, not something to slip into an audit PR.

Baseline recorded for future comparison: `989 passed, 31 skipped, 4 deselected` (33.0s);
`ruff check $LINT_PATHS` clean; `ruff check .` 1,870 findings; `npm ci && npm run build`
clean (964 KB JS).

---

## Backlog, ranked

| # | Item | Effort | Why it matters |
|---|---|---|---|
| 1 | Pick one frontend and retire the other two | **L** | Three parallel UIs, none complete, is worse than one unfinished UI. `server/frontend` has the best API client and the populated snapshot — it is the natural survivor. |
| 2 | Extend the lint allowlist beyond 13 files | **M** | 96% of the codebase is unchecked. Extend by directory (`pipeline/`, `federation/`, `integration/` are already clean) rather than attempting all 1,870 findings at once. |
| 3 | Add ESLint config + `lint` script to `server/frontend` | **S** | The only frontend in the federation with no linter at all. |
| 4 | Give `server/frontend` a router and real pages | **L** | 53.8k LOC of backend including SSE and GeoJSON services, surfaced through zero pages. |
| 5 | Add loading, empty, and error states | **M** | Currently 0 of each. `skywatcher-pr`'s `LoadingState`/`EmptyState` components are an in-house pattern to copy. |
| 6 | Add a frontend test runner | **M** | Zero tests across all three UIs. |
| 7 | Move reusable `scripts/` logic into `spiderweb/` | **L** | 11,987 LOC in scripts vs 1,592 in the package. |

**Recorded so it is not re-raised:** `server/backend/requirements.txt` is empty. Dependencies
live in `pyproject.toml` extras and CI installs `.[airspace,earthgpt,server,dev]`; nothing
reads that file. Not a defect. An earlier pass in this audit reported the test suite as
failing on a missing `sse_starlette` — that was an under-provisioned install on the auditor's
side, not a repo problem; with CI's extras the suite is fully green.
