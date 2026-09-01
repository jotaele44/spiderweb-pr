# spiderweb-pr — Improvement Recommendations

> **Historical audit.** This document records the repository shape observed
> before the current packaging and airspace-boundary work. FR24/RLSM/OCR items
> below are not active Spiderweb recommendations; executable ownership belongs
> to `skywatcher-pr`. Current dispositions live in
> `docs/FR24_EXECUTABLE_RETIREMENT.md` and `docs/REPO_BOUNDARY.md`.

_Generated 2026-05-29. Advisory only — no source code was refactored or deleted
in the change that introduced this document. Each item below is sized so the
maintainer can approve the higher-risk moves (packaging changes, monorepo split)
deliberately._

## Status update (2026-08-19)

Items #1, #2, #3, #4, #6, and #7 below are resolved on `main`: `pyproject.toml`
carries the correct project identity and a full `[project.optional-dependencies]`
extras split (`airspace`, `gebco`, `rag`, `earthgpt`, `imagery`,
`remote_monitoring`, `server`, `federation`, `geo`, `dem`, `spatial`, `all`,
`dev`), `requirements-*.txt` are now thin `-e .[extra]` shims, only `configs/`
exists (no leftover `config/`), `.pre-commit-config.yaml` is in place, and
`docs/README.md` is a real subsystem-grouped index. The snapshot table and
priority matrix below are left as historical record of what prompted the
work; they no longer describe the current state.

## Status update (2026-08-23) — item #5 resolved: no split

Item #5 (evaluate splitting gebco/earthgpt/llm into separate repos) is now
decided, with maintainer sign-off: **do not split.** Evidence gathered
against the current `main`:

- **Size**: ~3,185 combined LOC across `gebco/` (1,091), `earthgpt/` (1,586),
  and `llm/` (508) — small relative to the core (tens of thousands of LOC).
- **Coupling out**: zero imports from any of the three subsystems into the
  core (`pipeline.`, `federation.`, `server.`, `fr24.`, `readiness.`, etc.) —
  each is already a leaf package.
- **Coupling in**: `gebco` is imported by exactly 2 pipeline files (one
  lazily/guarded, adding no hard dependency); `earthgpt` has zero imports
  from `pipeline/`, `federation/`, `server/`, `readiness/`, or `spiderweb/`
  — it's only driven by its own dedicated `scripts/` CLI runners; `llm` has
  zero external references anywhere.
- **Federation**: `federation.json` and `federation/export_writer.py`/
  `envelope.py` reference none of the three — no cross-repo (thehub-pr)
  dependency on their internals.
- **CI**: already substantially isolated — `gebco` has its own dedicated
  test job, heavy `rag`/`llm` deps are excluded from CI via
  `importorskip`/mocks, and a per-extra `install-matrix` job already proves
  each extra (`gebco`, `earthgpt`, ...) installs and imports cleanly on its
  own.
- **Extras/README isolation** (the original ask's fallback option) is
  already done: separate `pyproject.toml` extras, matching
  `requirements-*.txt` shims, and subsystem READMEs all exist for all three.
- The row's other justification, an "embedded node app at
  `workbench/priis-v1/app`," is stale — that app was deleted three weeks
  before this document was generated (commit `fcb658b`, "Consolidate to one
  flight-free frontend and retire the airspace surface").

Conclusion: a full repo split (originally sized Large effort / Medium risk)
would buy negligible decoupling, since there's almost nothing left to
decouple. The item is closed as "isolation already sufficient, no split
warranted" rather than actioned as a split.

## Snapshot

| Metric | Value |
|--------|-------|
| Python files | ~205 |
| Python LOC | ~36k |
| Top-level subprojects | ≥6 (airspace/FR24, gebco, earthgpt, llm/RAG, `server/`, federation) |
| Test files | 58 |
| Dependency manifests | `pyproject.toml` + 5 `requirements-*.txt` + `requirements.txt` + `constraints.txt` |
| Largest source file | `pipeline/operational_intelligence.py` (35 KB) |
| CI workflows | 2 |
| Pre-commit | none |

**Strengths to preserve:** ruff + black config, thoughtful pytest markers
(`smoke` / `integration` with sensible default exclusions), 58 test files, and a
rich `docs/` set. The issues below are mostly about cohesion and packaging
correctness, not code quality in the individual modules.

## Priority matrix

| # | Area | Issue | Recommendation | Effort | Risk | Priority |
|---|------|-------|----------------|--------|------|----------|
| 1 | Upgrade/Fix | **Packaging identity mismatch**: `pyproject.toml` declares `name = "gebco-bathymetry-pipeline"` v0.1.0 with only gebco deps and `packages.find include = ["gebco*"]`, but ~90% of the code is the "Puerto Rico Airspace Intelligence System" (`pipeline/`, `server/`, `fr24/`, `readiness/`, `federation/`, `llm/`, `earthgpt/`). `pip install .` ships only gebco | Rename the project, fix `packages.find` to include the real packages, set an accurate description | S | Low | P0 |
| 2 | Upgrade | Conflicting / future-dated pins: `pyproject` `numpy>=2.4` vs `requirements.txt` `numpy>=1.26`; tight upper bounds (`pandas>=3.0,<3.1`, `numpy>=2.4,<2.5`, `xarray>=2026.1`, `pytest>=9.0.2`, `black>=26.3.0`) | Reconcile numpy/pandas across files to one source of truth; relax the narrow upper bounds to reduce resolver friction | S | Medium | P0 |
| 3 | Reorganize | **Fragmented dependencies**: 6 requirements files + `constraints.txt` + `pyproject` deps; `requirements.txt` re-bundles airspace+rag+earthgpt, overlapping the per-feature files | Consolidate into `pyproject` optional-dependency extras: `[airspace]`, `[gebco]`, `[rag]`, `[earthgpt]`; keep `constraints.txt` for exact pins only | M | Low | P1 |
| 4 | Reorganize | `config/` and `configs/` both exist (one holds `pr_intake_domain_router.yaml`, the other `georef_anchors.csv`) — easy to misread/misplace | Merge into a single `config/` directory; update references | S | Low | P1 |
| 5 | Remove/Split | Grab-bag monorepo: gebco bathymetry, earthgpt satellite, and llm/RAG are only loosely coupled to the airspace core; embedded node app at `workbench/priis-v1/app` | Evaluate splitting gebco/earthgpt/llm into separate packages/repos, or at minimum isolate them behind extras (#3) with their own READMEs | L | Medium | P2 |
| 6 | Improve | 28 docs files (many `FR24_*`) with no consolidated index beyond README links | Add `docs/README.md` index grouping by subsystem | S | Low | P2 |
| 7 | Improve | No pre-commit; CI lighter (2 workflows) than the federated peer | Add `.pre-commit-config.yaml` (ruff + black already configured) and `mypy`; bring CI to parity with moneysweep-pr | M | Low | P2 |

## Quick wins (low effort, low risk)

- **#1** Fix `pyproject.toml` identity and `packages.find` — restores a working install.
- **#4** Merge `config/` + `configs/`.
- **#6** Add a `docs/` index.

## Larger initiatives (plan + sign-off)

- **#3 dependency consolidation** — collapses 6+ manifests into `pyproject`
  extras; do this alongside **#1/#2** so there's a single dependency story.
- **#5 monorepo split / isolation** — resolved 2026-08-23, no split. See the
  "item #5 resolved" status section above for the evidence and decision.

## Cross-repo federation (shared with moneysweep-pr)

`spiderweb-pr` consumes moneysweep-pr's versioned "Contract-Finance" export
contract (currently v1.2.0) via `federation/hub/adapters/moneysweep.py`.
The version is bumped by hand across both repos. **Recommendation:** add an
automated contract-compatibility test — a golden schema fixture plus an explicit
version assertion — in both repos so a producer-side change can't silently break
this consumer. This is the highest-leverage cross-cutting improvement because it
protects the integration boundary both projects depend on.
