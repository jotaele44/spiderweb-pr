# Road to 100

Leverage-ordered ledger for closing the last stretch of `spiderweb-pr` to a
100%-ready state. Companion to [`ROI_TASK_LEDGER.md`](ROI_TASK_LEDGER.md),
[`NEXT_100_TASKS_V2.md`](NEXT_100_TASKS_V2.md), and
[`RELEASE_READINESS.md`](RELEASE_READINESS.md).

**Current completion: ~85%.** This document separates what is **code-closable
offline** (done here, or trivially doable) from what is **data- or
network-blocked** (grows only as live intake runs), so nobody mistakes a
data-availability ceiling for an unfinished code path.

Last updated **2026-07-12**.

---

## Where the 85% comes from (already landed)

- **Real (small) spatial streams** — 10 observations across 2 sources, kept
  deliberately "small-but-real" (no fabricated points; see
  [`DATA_POLICY.md`](DATA_POLICY.md)).
- **Hub `validate-package` → VALID** — federation envelope passes.
- **USGS OFR 98-038 geodata baseline** — metallic-occurrence layer converted to
  WGS-84 with full provenance (`data/usgs_ofr_98_038/`).
- **Mature hygiene** — `Makefile`, `.pre-commit-config.yaml`, `CHANGELOG.md`.
- **76 test files** under `tests/` (68 `test_*` modules + fixtures/helpers).

---

## Remaining — code (CLOSED in this PR)

Leverage-ordered. All three were offline-closable and are done here.

### 1. Untrack committed `server/frontend/node_modules/` (~3,598 files) ✅
Highest leverage: removes ~3.6k vendored files from version control, shrinks
clones, and stops dependency churn from polluting diffs.

- `git rm -r --cached server/frontend/node_modules` (working-tree copy kept).
- `.gitignore` gains a general `**/node_modules/` guard plus the explicit
  `server/frontend/node_modules/` path so it can never be re-committed.
- **Verify:** `git diff --cached --name-only | grep node_modules` shows only
  deletions (3,598 `D`); `git ls-files | grep -c node_modules` → `0`; the files
  remain on disk (`ls server/frontend/node_modules`).

### 2. Replace hardcoded `infra_align = 0.3` placeholder ✅
File: `integration/ilap_airspace_bridge.py`.

The POI confidence model weights an `infra_align` term at 0.20. It was a bare
magic constant (`0.3  # placeholder; real impl would cross-ref infra layer`).

- Introduced `infra_alignment_score(points)` — a **pure, deterministic,
  offline** proxy computed from the covariance eigenvalues of the POI cluster's
  own points: `linearity = (λ1 − λ2) / (λ1 + λ2)`, which is `1.0` for a
  collinear cluster (points tracing a linear feature — road/pipeline/coast) and
  `~0.0` for an isotropic blob (loiter around a single site). Degenerate inputs
  (<2 usable points, zero spread, `(0,0)` sentinels, missing coords) → `0.0`.
- Emitted GeoJSON now carries `"infra_alignment_method":
  "geometry_covariance_proxy"` so the value is never presented as an external
  infra cross-reference.
- **Unit tests** added in `tests/test_spiderweb_bridge.py` (collinear→1,
  isotropic→0, elongated strictly in (0,1), bounded output, degenerate→0,
  missing-coord rows skipped).

**Residual (data-blocked — see below):** the *intended* signal is a cross-ref
against a real PR **infrastructure vector layer** (roads / transmission /
pipelines). The repo ships no such layer today — only the USGS OFR 98-038
mineral points and the 72-municipality centroid set — so the true external
cross-reference remains data-blocked. The geometry proxy is the honest,
computable-now stand-in and is documented as such in code and here.

### 3. Implement / guard the two `NotImplementedError`s ✅
Both were **bare, message-less** raises on genuinely abstract interface methods.
Neither has a network-free generic implementation (each is an extension point),
so both were converted into **explicit typed guards** that name the offending
subclass and point at the contract — the documented-extension-point pattern.

- `scripts/_harvest_base.py` — `HarvestBase.normalize_row` (per-source raw
  schema; no generic impl possible). Guard names `type(self).__name__` and
  references the `CANONICAL_COLUMNS` contract.
- `scripts/geocode_pr.py` — `Backend.geocode` (abstract provider interface).
  Guard names the subclass and points to `CensusBackend` / `NominatimBackend` /
  `FixtureBackend`; notes that offline-only deployments should use
  `FixtureBackend` or `CachedBackend`'s on-disk cache.

---

## Remaining — data / network-blocked (NOT closable offline)

These do not represent unfinished code; they are gated on live data intake or
external layers that cannot be fetched in an offline, no-fabrication run.

- **Corpus is intentionally "small-but-real."** It grows only as intake runs
  live (`run_pr_intake_router.py` and the per-source harvesters). No synthetic
  observations are added to inflate counts — that is a policy, not a gap.
- **`infra_align` external cross-reference.** Needs a real PR infrastructure
  vector layer (roads/utilities/pipelines) to replace the geometry proxy with a
  true spatial cross-ref. Blocked on sourcing + licensing that layer offline.
- **`hydro_utility` term** in the same confidence model is still a fixed `0.2`.
  It has the same external-layer dependency (hydrology / utility corridors) and
  is left as-is here rather than dressed up as a computed value. Tracked for the
  same infra-layer intake.
- **Second 100-task optimization sweep** (`NEXT_100_TASKS_V2.md`,
  `ROI_TASK_LEDGER.md`) is largely landed — the ROI ledger's
  *"NEXT_100_TASKS_V2 roadmap — Themes 2–12"* table records every theme as
  ✅ complete — **but a genuine re-read against the `Blockers` column of
  `NEXT_100_TASKS_V2.md` shows the sweep still has offline-closable items open.**
  Only the items with a **real external / data / dependency blocker** belong in
  the blocked list below; the ones the V2 doc marks `Blockers = None` are ordinary
  offline work and are listed under *"remaining — offline-closable"* instead (see
  that section), so operators are not steered away from actionable robustness /
  security work.

  **Genuinely blocked (real blocker named in `NEXT_100_TASKS_V2.md`):**
  - #68 pixel-CV flight-track v2 — `Blockers = #69` (chained on the anchor work).
  - #72 OCR confidence recalibration — `Blockers = Labeled set` (needs labeled
    ground truth).
  - #73 multi-engine ensemble vote — `Blockers = Engines installed` (needs extra
    OCR engines present).
  - #76 hub rtree spatial index — `Blockers = rtree` (needs the `rtree`
    dependency, not vendored offline).
  - #77 envelope version-negotiation — `Blockers = #14` (chained on the envelope
    schema work).

  This pass closed one concrete offline item: a direct unit test for the public
  `integration/mbil.is_mbil_high` helper (it gates the `aasb_mbil_corridor_flag`
  but had only indirect coverage), added as
  `tests/test_gis_upgrades.py::test_is_mbil_high_truth_table`. The remaining
  offline-closable items below are **left open, not fabricated as closed** —
  implementing them is larger work beyond this surgical audit pass.

---

## Remaining — offline-closable (V2 sweep, open — NOT blocked)

These V2 tasks carry `Blockers = None` in `NEXT_100_TASKS_V2.md`: they are
actionable offline **now** and are simply not yet implemented. They are tracked
here as open work (not data/network-blocked) so nobody skips them under the
mistaken belief the sweep has zero remaining offline code. Implementing them is
larger than this audit pass, which deliberately closed only the small
`is_mbil_high` test gap.

| # | Task | Theme | Effort | Why it is offline-doable |
|---|---|---|---|---|
| #81 | Typed error taxonomy (replace bare excepts) | 10 — Observability | 3 h | Pure refactor of in-repo exception handling; no external input. |
| #84 | Checkpoint / resume files for long runs | 10 — Observability | 3 h | Local checkpoint I/O; exercised on any run, no live corpus required. |
| #89 | Data-policy redaction lint on exports | 11 — Security | 3 h | Enforces `DATA_POLICY.md` rules over already-exported files; static check. |
| #62 | Map-preview PNGs per GeoJSON | 7 — GIS | 3 h | Headless matplotlib render of local GeoJSON (skip network basemap tiles). |
| #64 | GeoPackage (`.gpkg`) export | 7 — GIS | 2 h | Single-file offline geo write from data already in hand. |
| #69 | Geo-anchors v2 (OCR-matched POIs → homography) | 8 — RLSM | 8 h | `Blockers = None`; runs over screenshots already ingested in the DB. |
| #92 | `LICENSE` / SPDX headers | 12 — Docs | 1 h | Adding the file is offline; only the license *choice* is an owner decision. |

## Leverage-ordered checklist

| # | Item | Leverage | State |
|---|---|---|---|
| 1 | Untrack `node_modules/` (~3.6k files) + gitignore guard | High | ✅ closed (code) |
| 2 | `infra_align` geometry proxy + unit tests | High | ✅ closed (code); external cross-ref data-blocked |
| 3 | Two `NotImplementedError`s → typed extension-point guards | Medium | ✅ closed (code) |
| 4 | Source a real PR infrastructure vector layer | High | ⛔ data-blocked |
| 5 | `hydro_utility` real computation (same layer dep) | Medium | ⛔ data-blocked |
| 6 | Grow corpus via live intake runs | High | ⛔ intake-gated (by design) |
| 7 | Finish V2 optimization sweep (non-data items) | Low–Med | ◻ partly open — one offline test gap (`is_mbil_high`) closed this pass; #81/#84/#89/#62/#64/#69/#92 remain offline-closable and open; #68/#72/#73/#76/#77 are genuinely blocked |

**Items 1–3 (the offline code-closable set) closed in the prior merged audit
PR. Items 4–6 remain data/network-blocked. Item 7: after a full re-read of
`NEXT_100_TASKS_V2.md` + `ROI_TASK_LEDGER.md` — checked against each task's
`Blockers` column — the sweep still has offline-closable robustness/security/GIS
work open (#81 error taxonomy, #84 checkpoint/resume, #89 data-policy lint, #62
map-preview, #64 GeoPackage, #69 geo-anchors v2, #92 LICENSE; all `Blockers =
None`). This pass closes one small offline gap — a direct unit test for
`mbil.is_mbil_high` — and leaves the larger offline items honestly OPEN. Only
#68/#72/#73/#76/#77 (real named blockers) are classified blocked. The V2 sweep
is NOT claimed to have zero remaining offline work.**
