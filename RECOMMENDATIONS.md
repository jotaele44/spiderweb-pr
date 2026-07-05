# spiderweb-pr — Improvement Recommendations

_Generated 2026-05-29. Advisory only — no source code was refactored or deleted
in the change that introduced this document. Each item below is sized so the
maintainer can approve the higher-risk moves (packaging changes, monorepo split)
deliberately._

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
- **#5 monorepo split / isolation** — the biggest structural decision. Decide
  whether gebco/earthgpt/llm are first-class members of this repo or separate
  products; the answer drives packaging, CI, and docs. Sequence it after #3 so
  each candidate already has a clean extras boundary.

## Cross-repo federation (shared with moneysweep-pr)

`spiderweb-pr` consumes moneysweep-pr's versioned "Contract-Finance" export
contract (currently v1.2.0) via `federation/hub/adapters/moneysweep.py`.
The version is bumped by hand across both repos. **Recommendation:** add an
automated contract-compatibility test — a golden schema fixture plus an explicit
version assertion — in both repos so a producer-side change can't silently break
this consumer. This is the highest-leverage cross-cutting improvement because it
protects the integration boundary both projects depend on.
