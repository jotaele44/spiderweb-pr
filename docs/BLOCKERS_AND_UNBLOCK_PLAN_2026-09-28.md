# Blockers and unblock plan — spiderweb-pr (2026-09-28)

**Audit date:** 2026-09-28 · **`main` at audit:** `7bba026` (branch-protected) · **Production status:** `PRODUCTION`. Since #392, `export_canonical` exports the committed real streams: 874 rows, 0 synthetic.

This document lists every blocker that the repository, its CI, and its GitHub issues and pull requests recorded as of the audit date, then gives an ordered plan to clear them. It changes no code, gate, ledger, or status file.

Cross-repository blockers (IDs `X-nn`) are described in full in
`jotaele44/thehub-pr` → `docs/BLOCKERS_AND_UNBLOCK_PLAN_2026-09-28.md`.

## How this inventory was built

Sources checked:

- the 1 open issue and all 9 open pull requests;
- CI on `main`, for push and scheduled runs (`JP flood V3 live drift`, `PR Hydrography Acquisition`, maintenance, pip-audit, CodeQL, secret scan: all green on their latest runs);
- per-PR check results from the thehub federation completion-gate artifact (run `36326861596`);
- `docs/unfinished_implementation_ledger.v1.json`, reconciled against PR history;
- `docs/ROAD_TO_100.md`, `docs/LOCATION_QUERY_AUDIT_2026-09-17.md`, `docs/RELEASE_READINESS.md`, `AUDIT.md`;
- thehub `docs/FEDERATION_MAX_AUDIT_2026-09-24.md` and `docs/FEDERATION_UI_OPERATIONS_FAILURE_LEDGER.csv`;
- a code scan of the working tree for error types, geo-anchors v2 and SPDX headers;
- the branch list and branch protection.

## Summary

Each blocker is counted once, under its primary type.

| Type | Count |
|---|---:|
| GATE | 2 |
| IMPL | 5 |
| DATA | 3 |
| PR | 1 group (9 PRs) |
| STALE | 1 |
| **Total** | **12** |

## Blocker inventory

| ID | Blocker | Type | Evidence | Owner | Unblock step | Exit criterion |
|---|---|---|---|---|---|---|
| SW-01 | No GUI-capability-parity gate | GATE | thehub MAX audit F1 addendum: spiderweb is the only producer without `.github/workflows/gui-capability-parity.yml`. Ledger SPW-002: the older candidate #237 carried a legacy baseline of 1,016 signals. The same timeline component landed here unchecked. | Agent | Adopt the federation parity gate with a classified baseline (ratchet: no new debt) | Parity workflow required on `main` |
| SW-02 | No typed error taxonomy | IMPL | Ledger SPW-003. There is no Spiderweb base error class, and `spiderweb/`, `pipeline/` and `scripts/` contain 88 broad `except Exception` clauses. `docs/ROAD_TO_100.md` ranks this first ("before expanding live ingestion"). | Agent | Introduce a typed hierarchy and migrate the broad handlers with tests | Broad or bare handlers replaced; stable error reporting |
| SW-03 | Geo-anchors v2 not implemented | IMPL | Ledger SPW-007: no implementation in the tree | Agent | Implement OCR-matched anchors with bounded homographies and rejection evidence | Anchors produce homographies with uncertainty |
| SW-04 | No licensing or SPDX metadata | IMPL | `docs/ROAD_TO_100.md` lists licensing/SPDX as an implementation gap; 0 source files carry `SPDX-License-Identifier` | Agent/maintainer | Choose a header policy and add SPDX identifiers | SPDX coverage check passes |
| SW-05 | Standalone packaging is not certified | GATE | Ledger SPW-001: #243 merged, current-`main` certification pending | Agent/maintainer | Certify install, test, frontend and desktop packaging from `main` | Packaging receipt |
| SW-06 | Scores still use fixed hydrology and infrastructure proxies | DATA | Ledger SPW-008 | Operator | Obtain licensed, provenance-bound infrastructure and hydrology layers | Scores derive from authoritative layers |
| SW-07 | LOCATION_QUERY provider denominator is still open: (1) SSURGO Stage-1 plus MUKEY → component receipts; (2) 3DHP FeatureServer denominator; (3) FEMA NFHL and PR ABFE layer denominators; (4) USACE general service-root closure; (5) place-resolver candidate binding; (6) Húcar, San Juan and Boquerón reference AOIs. Also: the `PRVI_1m_DEM_2018` provider binding is still `PROVIDER_BINDING_OPEN`, and Sentinel Hub and Copernicus CDSE are `READY_WITH_CREDENTIALS` | DATA/IMPL | `docs/LOCATION_QUERY_AUDIT_2026-09-17.md` ("Open implementation denominator" and the provider table). Draft #387 (green) closes post-merge residue. | Agent with network + operator (credentials) | Execute each denominator freeze in a network-enabled runner; provision the imagery credentials if those lanes are wanted | Every provider is READY or explicitly excluded, with receipts |
| SW-08 | Ferrocarril rows are uncertified | DATA | #269: all 609 source rows are `PROVISIONAL`; 0/609 have exact coordinates | Agent/analyst | Row-level provenance → georeferencing → entity adjudication → promotion gate (per the issue) | Every row classified; crosswalk arithmetic closes |
| SW-09 | Producer schemas collide with hub canonical names | IMPL | thehub MAX audit F11: `federation_entity`, `federation_relationship` and `federation_source` reuse the hub filenames for a narrower dialect (`extraction_method` lineage, closed enums, `additionalProperties: false`) | Agent | Rename them to producer-local names | No same-name schema with different semantics |
| SW-10 | Some frontend controls do nothing | IMPL | `docs/ROAD_TO_100.md`: inert filters, cursor, investigation selection, query adapter and graph surfaces are "not counted as complete controls" | Agent | Wire each control, or remove it or mark it diagnostic | No inert controls in the parity inventory |
| SW-11 | Open PRs | PR | See the next table | Agent + maintainer | Per-PR actions below | No red PRs |
| SW-12 | Stale docs and trackers | STALE | (a) `AUDIT.md` calls `server/backend/production.py` a "stub"; it is a deliberate 372-byte composition entrypoint that mounts the Martin router. (b) The LOCATION_QUERY audit still says "BLOCKED_ACTIONS_INFRASTRUCTURE", but runners have been restored since 2026-09-19. (c) thehub UI-ops ledger row F019 says this repo lacks `scripts/validate_schemas.py`, but that script exists since #290 (`95d97ca`, 2026-09-03) and `federation.json` declares it as `validate_schemas`. Only the `make validate-schemas` target still inlines `python -c`. | Agent | Correct (a) and (b) here; update F019 in thehub; optionally point the Makefile target at the script | Docs accurate |

### Open pull requests (SW-11)

| PR | State | Action |
|---|---|---|
| #387 LOCATION_QUERY exact-spatial residue (draft) | Head checks green (44) | Mark ready, update the branch, merge |
| #381 prawcore 4, #380 mcp 2.2, #379 filelock 4, #378 fastmcp-slim 4 | Green, but all majors | Review the API changes, update the branch, merge |
| #377 python minor/patch group (65 updates), #375 vitest 5 | Green | Update the branch and merge |
| #376 actions minor/patch group | RED: Federation template drift | Land the bump via thehub `federation-templates`, re-render, close this PR |
| #374 npm minor/patch group | RED: builds × 3, frontend, workbench-matrix | Find the offending package, split the group or pin it |

## Unblock plan

### P1 — executable now
1. **SW-01:** add the GUI-parity gate.
2. **SW-11:** merge #387 and the green dependency PRs; route #376 through the templates; bisect #374.
3. **SW-12:** correct the stale docs, and have thehub update ledger row F019.

### P2 — operator inputs
1. **SW-06:** authoritative hydrology and infrastructure layers.
2. **SW-07:** imagery credentials and network-enabled denominator freezes.

### P3 — maintainer decisions
1. **SW-04:** licensing and SPDX policy.
2. **SW-09:** schema renaming (coordinate with thehub).

### P4 — longer horizon
1. **SW-02:** typed errors (first, per the road to 100).
2. **SW-03:** geo-anchors v2.
3. **SW-10:** frontend inert controls.
4. **SW-05:** packaging certification.
5. **SW-08:** Ferrocarril canonicalization.

## Ledger reconciliation (`docs/unfinished_implementation_ledger.v1.json`, dated 2026-08-04)

| Ledger ID | Ledger state | State on 2026-09-28 |
|---|---|---|
| SPW-001 | merged_certification_pending | Still open → SW-05 |
| SPW-002 | stale_unmergeable_pr (PR-237) | Still open: there is no parity gate on `main` → SW-01 |
| SPW-003 | main_gap | Still open → SW-02 |
| SPW-004, SPW-005, SPW-006 | closed_merged | Closed |
| SPW-007 | main_gap | Still open → SW-03 |
| SPW-008 | external_data | Still open → SW-06 |

## Cross-repo note
- The JP-flood receipts consumed by thehub are healthy on this side: the latest PASS is run `36328607066` at `bb8463c`. The failing freshness check is a stale pin in thehub (X-04).

## Hygiene
- 38 branches on origin, including `rescue-stash-4`, several `audit/*` branches, and `claude/gis-code-audit-fd57wm` (identical to `chatgpt/spiderweb-write-guard-20260916`).

## Federation-wide blockers that affect this repo
- X-01: completion gate.
- X-02: dependabot backlog and template drift.
- X-04: JP-flood pin in thehub.
- X-07: stale ledgers.

See the thehub document for details.

## Not verifiable with the access used for this audit
- Code-scanning and Dependabot security-alert inventories.
- Actions secrets.
- Operator-local retained databases (`docs/RELEASE_READINESS.md` evidence-chain coverage).
