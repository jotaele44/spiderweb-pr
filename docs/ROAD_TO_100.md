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
  `ROI_TASK_LEDGER.md`) is functionally landed: the ROI ledger's
  *"NEXT_100_TASKS_V2 roadmap — Themes 2–12"* table records every theme as
  ✅ complete (schema/validation, Spiderweb language, perf, testing, CI, GIS,
  RLSM, federation, observability, security, docs), and the ledger's *"Deferred"*
  note enumerates the leftovers that are **not** offline-closable code:
  - #68 / #69 pixel-CV flight-track + geo-anchor v2 — need labeled screenshot
    pixels + homography ground truth (live-intake-gated).
  - #72 / #73 OCR confidence recalibration + multi-engine ensemble — need a
    labeled ground-truth set and additional OCR engines installed.
  - #76 hub rtree spatial index + #77 envelope version-negotiation — federation
    scale/handshake features gated on a live multi-hub deployment.
  - #62 / #64 contextily / geopandas map-preview + GeoPackage exports — heavy
    geospatial-stack dependencies not vendored offline.
  - #81 error taxonomy, #84 checkpoint/resume, #89 data-policy redaction lint —
    exercised only against live multi-hour runs / real export corpora.
  - #92 LICENSE / SPDX — an owner (licensing) decision, not a code gap.

  After a full re-read of both V2 docs, the **only** remaining concrete
  offline-closable code item found was a direct unit test for the public
  `integration/mbil.is_mbil_high` helper (it gates the `aasb_mbil_corridor_flag`
  but had only indirect coverage). That test is added in this PR
  (`tests/test_gis_upgrades.py::test_is_mbil_high_truth_table`). No other
  non-data, offline-closable code work remains in the V2 sweep — the rest is the
  data/network-blocked set enumerated above, so no closure is fabricated for it.

---

## Leverage-ordered checklist

| # | Item | Leverage | State |
|---|---|---|---|
| 1 | Untrack `node_modules/` (~3.6k files) + gitignore guard | High | ✅ closed (code) |
| 2 | `infra_align` geometry proxy + unit tests | High | ✅ closed (code); external cross-ref data-blocked |
| 3 | Two `NotImplementedError`s → typed extension-point guards | Medium | ✅ closed (code) |
| 4 | Source a real PR infrastructure vector layer | High | ⛔ data-blocked |
| 5 | `hydro_utility` real computation (same layer dep) | Medium | ⛔ data-blocked |
| 6 | Grow corpus via live intake runs | High | ⛔ intake-gated (by design) |
| 7 | Finish V2 optimization sweep (non-data items) | Low–Med | ✅ audited — sole offline item (mbil `is_mbil_high` direct test) closed; remainder data/network-blocked |

**Items 1–3 (the offline code-closable set) closed in the prior merged audit
PR. Items 4–6 remain data/network-blocked. Item 7: after a full re-read of
`NEXT_100_TASKS_V2.md` + `ROI_TASK_LEDGER.md`, the V2 sweep's themes are recorded
complete and its only remaining offline-closable code gap — a direct unit test
for `mbil.is_mbil_high` — is closed in this PR; every other leftover is
data/network-blocked (enumerated above) and is deliberately NOT fabricated as
closed.**
