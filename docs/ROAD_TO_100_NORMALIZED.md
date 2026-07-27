# Spiderweb-PR — Normalized Road to 100 Status

**Governance version:** `road_to_100_normalization_v0_2`  
**Audit date:** 2026-07-27  
**Evidence boundary:** repository `main`, canonical `federation.json`, `docs/ROAD_TO_100.md`, `docs/MATURITY_AUDIT.md`, and recorded executed baselines.  
**Status mutation:** none. This document does not change `production_status` or federation readiness gates.

## Normalized scorecard

| Metric | Value | Interpretation |
|---|---:|---|
| Implemented scope | **85% — core pipeline scope only** | The value applies to the core spatial/operational pipeline and its declared extension points. It is not an overall repository-readiness percentage. |
| CI-enforced maturity | **56%** | Derived from the 20-criterion professional maturity audit. |
| Operational data readiness | **30%** | Audit estimate reflecting a valid but very small real package: 10 observations across 2 sources, with recurrent intended-scope intake unproven. |
| Live-gate evidence depth | **D1 — small real seed corpus** | A production package validates and the live gate is true, but corpus depth and recurring intake evidence are limited. |
| Current live-execution gate | **true** | Preserved from `federation.json`; not altered by this normalization. |

## Verification anchor

- **Last verified `main` commit:** `ef2701ee626e538d2c188e4b9e40283d72ae503d`
- **Last executed test baseline:** `989 passed, 31 skipped` in the federation maturity audit.
- **Evidence confidence:** high for implementation and CI maturity; medium for operational readiness because the current production package is intentionally small.

## Correction to the legacy 85% label

The legacy roadmap's `~85%` figure is retained only as **core pipeline scope completeness**. It must not be interpreted as professional maturity or operational data coverage. The 29-point gap to the 56% maturity score is the largest in the federation and is explained by concrete open work:

1. Ruff/Black/mypy cover only a small allowlist rather than the repository-wide Python surface.
2. There is no complete, consolidated frontend and no frontend test runner.
3. Multiple offline-closable V2 tasks remain open: typed error taxonomy, checkpoint/resume, export redaction lint, map previews, GeoPackage export, geo-anchors v2, and license/SPDX policy.
4. The production corpus is small and does not yet demonstrate recurring intended-scope intake.
5. Infrastructure and hydrology cross-reference terms still depend on external authoritative layers.

## Evidence-depth scale

- **D0:** synthetic or no production corpus; no live production export.
- **D1:** small real seed corpus; production package may validate, but recurrent intake is unproven.
- **D2:** partial real intended-scope corpus and bounded live runs; important source or freshness gaps remain.
- **D3:** recurring real intake and valid production export with material provenance or coverage caveats.
- **D4:** recurring intended-scope live intake, freshness controls, production export, and consumer validation.

The detailed implementation narrative remains in [`ROAD_TO_100.md`](ROAD_TO_100.md). This normalized companion controls cross-repository comparisons.