# D18 — Dependency-directed implementation queue

Nothing in this queue has started. Each item names what it needs first. Items
with no unmet need can run in parallel. "Owner decision" marks an item that
waits on the repository owner, not on work.

## Stage 0 — Blockers to clear before any acquisition

| ID | Item | Needs |
|---|---|---|
| Q01 | Guard the two `extractall` calls against paths that leave the target directory (D15) | — |
| Q02 | Put the unrestricted fetch paths behind a host allow-list (D15) | — |
| Q03 | One owner for map view state; remove the second writer of the URL fragment (D11) | — |
| Q04 | Amend the diagnostic-only rule (see the decision record) | Owner decision; thehub-pr change |
| Q05 | Attach skywatcher-pr and recover the SATIM annotation contract and colour convention | Owner decision (access) |
| Q06 | Confirm licence terms for the pilot provider's files | — |

## Stage A — Canonical foundation

| ID | Item | Needs |
|---|---|---|
| A01 | Index over the seven source registries (read-only; no merge) | — |
| A02 | Dataset version registry, seeded with the two pilot versions; one spelling of dataset identity, taken from the elevation catalogue | A01 |
| A03 | Asset ledger generalised from the pilot file; lot recorded on the asset (gap 004); alternates recorded between sets (gap 006) | A02; owner decision on gaps 004 and 006 |
| A04 | Segment review record on Grid V2 cells | — |
| A05 | Re-point the two files still blocked on the first grid at Grid V2 | A04 |
| A06 | Bind pilot asset identifiers to thehub-pr's identifier contract | A03 |

## Stage B — Acquisition

| ID | Item | Needs |
|---|---|---|
| B01 | Provider retrieval handler for the ledger, reusing `DownloadSession` controls | Q01, Q02 |
| B02 | Interrupted-transfer tests against a local server; one real file | B01 |
| B03 | Free-disk admission before a claim | — |
| B04 | Supervised worker and restart test | — |
| B05 | Planner: order assets by segments unlocked | A03 |
| B06 | Acquire the pilot's zone 19N files (14 files, 3.3 GB) | B01 to B05; **product download grant** (owner decision); Q06 |
| B07 | Valid-data extent per file; restate coverage (gap 003) | B06 |
| B08 | Reboot test on a real machine; lift the withholding in D16 if it passes | B04 |

## Stage C — Comparison

| ID | Item | Needs |
|---|---|---|
| C01 | Eligibility resolver over the eleven checks; unevaluable means blocked | A03 |
| C02 | Carry the open vertical datum conflict on every comparison record; resolve it if a benchmark tie becomes available | — |
| C03 | Qualify the existing elevation comparison (`scripts/run_dem_vs_3dep_lidar.py`) for per-segment, version-to-version use; bind its existing result at tile position x81y203 to segments | B06 |
| C04 | Run it per segment through the ledger; store comparison records | C01, C03 |
| C05 | Discrepancy records and gap lifecycle | A04 |
| C06 | Observation records bound to asset, panel, comparison | Q05 for imagery; none for elevation |
| C07 | Segment disposition and local qualification record | C04, C05 |

## Stage D — Interface

| ID | Item | Needs |
|---|---|---|
| D01 | `/geo-sar` read routes over the registry files | A03 |
| D02 | `/geo-sar` job routes over the ledger, with event stream | — |
| D03 | `GeographicContext` and selection toolbar | Q03, Q04 |
| D04 | `ComparisonPanel`, mounted twice, with cascading selectors | D01, D03 |
| D05 | Synchronisation controller | Q03, D04 |
| D06 | Not-acquired state and acquire control | D02, D04 |
| D07 | Results table, segment navigation | C04, D04 |
| D08 | Mosaic matrix, derived | C07, D01 |
| D09 | Annotation layer | Q05, C06 |
| D10 | Tablet and phone layouts in the browser matrix | D04 |
| D11 | Remaining consoles and registries (assets, gaps, execution, storage) | D01, D02 |

## Stage E — Federation

| ID | Item | Needs |
|---|---|---|
| E01 | Propose the gap taxonomy and a qualification receipt schema to thehub-pr | Owner decision |
| E02 | An admission route for acquisition jobs in thehub-pr, or a recorded decision that the local ledger stands | Owner decision |
| E03 | Reconcile renderer versions with thehub-pr's lock | Owner decision |
| E04 | Export bindings for the other producers | Their repositories attached |

## Stage F — Qualification

| ID | Item | Needs |
|---|---|---|
| F01 | End-to-end scenario (directive §23) on the pilot, with real records | B06, C07, D08 |
| F02 | Exact-head continuous integration on the pull request | every stage |
| F03 | LOCKSTEP and consumer pins | E02; note D14 on what LOCKSTEP currently checks |

## Critical path

Q01, Q02 → B01 → B02 → **grant** → B06 → B07 and C03 → C04 → C07 → D08 → F01.

The interface work (D01 to D06) does not wait on acquisition and can proceed
alongside it once Q03 and Q04 are settled.

## Owner decisions that gate the queue

1. Product download grant for the pilot: 14 files, 3,310,696,836 bytes (or all
   28 files, 6,601,968,792 bytes).
2. Amending the diagnostic-only rule (Q04).
3. Access to skywatcher-pr (Q05), and to the other producers for E04.
4. Whether a 2018 lot is part of asset identity (gap 004), and at what unit
   "alternate" is asserted (gap 006).
5. Whether the local ledger stands or is replaced by a Federation route (E02).
