# D19, D20 — Exact-head baseline and preparation qualification dossier

FED-GEO-SAR-001, preparation stage. Written 2026-11-26.

## GOAL

Establish, with evidence, what the three repositories already provide for a
segmented geographic acquisition and review engine; fix the contracts and the
pilot; measure persistent execution; and state whether implementation can be
admitted.

**Outcome: implementation admission is not requested.** 65 of 110 preparation
gates pass. The rest are partial, open or blocked for the reasons listed
under GAPS. The pilot is fully prepared and persistent execution is measured,
so the pilot's acquisition stage could be admitted on its own if the owner
chooses; that is a narrower decision than admitting the programme.

## D19 — Exact-head baseline

| Repository | Head read | State when read |
|---|---|---|
| spiderweb-pr | `00ce0f9e8fec2a5c764881bf71ec00915583eb60` (main) | Clean |
| thehub-pr | `36a08974dda53c971c2283f019318e17a14d43df` (main) | Clean; not changed by this work |
| mucaro-ai | `13ad436668dbc26712ec53b163e64dcf972e16d0` (main) | Clean; not changed by this work |

Implementation starts from the commit that adds this file, on branch
`claude/gallant-thompson-uamoff` of spiderweb-pr, whose parent is the main
head above. The pull request records that commit.

Work in flight elsewhere that touches this programme:

| Where | What | Relevance |
|---|---|---|
| spiderweb-pr branch `feat/aoi-acquisition-workbench` | Area-of-interest selector and catalogue work, unmerged since September | Overlaps the selection toolbar; not evaluated in detail |
| spiderweb-pr main; run dated 2026-11-24 | Comparison of the 2024 and 2018 lidar surveys at eight sites | Already covers one pilot tile position; the pilot's comparison method (D18 C03) |
| spiderweb-pr branch `claude/ilap-lidar-change-screen` | Island-wide change screen of the same two surveys | Unmerged; not evaluated |
| spiderweb-pr pull request 419 | Native reference exports for another provider | Merge blocked; independent |
| mucaro-ai pull request 343 | Draft supervisor proof worker | The nearest Federation alternative to the local ledger |

Verification at this baseline plus the change:

| Check | Result |
|---|---|
| Full test suite, as continuous integration runs it | 2979 passed, 58 skipped, 4 deselected |
| Durability suite | 12 passed, four consecutive runs |
| Pilot suite | 30 passed |
| Offline replay of discovery | Reproduces the ledger exactly |
| Registry files against their schemas | 4 of 4 valid |

## GATES

| Phase | PASS | PARTIAL | OPEN | BLOCKED | UNVERIFIED | WITHHELD | Gates |
|---|---|---|---|---|---|---|---|
| 00 — Environment admission | 9 | 0 | 1 | 0 | 0 | 0 | 10 |
| 01 — Existing capability discovery | 19 | 0 | 0 | 1 | 0 | 0 | 20 |
| 02 — Internal dataset recovery | 2 | 4 | 1 | 2 | 1 | 0 | 10 |
| 03 — Architecture reconciliation | 5 | 2 | 3 | 0 | 0 | 0 | 10 |
| 04 — Contract preparation | 2 | 9 | 2 | 1 | 0 | 0 | 14 |
| 05 — GUI preparation | 1 | 14 | 0 | 1 | 0 | 0 | 16 |
| 06 — Pilot preparation | 15 | 0 | 0 | 0 | 0 | 0 | 15 |
| 07 — Implementation admission | 12 | 2 | 0 | 0 | 0 | 1 | 15 |
| **All** | **65** | **31** | **7** | **5** | **1** | **1** | **110** |

No single readiness percentage is given: the gates are not of equal weight and
a partial specification is not a fraction of a pass.

### Phase 00 — Environment admission

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 001 | Connected execution environment | PASS | Cloud container, 59 GB free, 4 cores, 15 GB memory |
| 002 | Repository identity | PASS | `jotaele44/spiderweb-pr`, `thehub-pr`, `mucaro-ai` attached |
| 003 | Spiderweb exact main head | PASS | `00ce0f9e8fec2a5c764881bf71ec00915583eb60` |
| 004 | Candidate branches and open pull requests | PASS | 53 branches and 6 open pull requests listed; four relevant ones named below |
| 005 | Local worktrees | PASS | One worktree per repository |
| 006 | Uncommitted user changes preserved | PASS | None existed in any of the three |
| 007 | Execution and storage resources | PASS | As 001 |
| 008 | Existing persistent job infrastructure recovered | PASS | D14: two stacks found, neither accepts this job class |
| 009 | Durable preparation job identity | OPEN | This preparation ran in a conversation session, not under a durable job. Its durable record is the branch and pull request. |
| 010 | Evidence preservation location | PASS | `evidence/geo_sar/` |

### Phase 01 — Existing capability discovery

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 011 | Geographic architecture audited | PASS | D01 |
| 012 | Source registries recovered | PASS | D02: seven |
| 013 | Dataset manifests recovered | PASS | D02 |
| 014 | Dataset version registries recovered | PASS | D01 B03: none exists |
| 015 | Original filename inventories recovered | PASS | D02 |
| 016 | Native tile inventories recovered | PASS | D02: 28 files, one family |
| 017 | Footprint registries recovered | PASS | D02: 8 of 28 footprints existed |
| 018 | Acquisition adapters recovered | PASS | D01 B09 to B11 |
| 019 | Spatial indexing recovered | PASS | D04: Grid V2 |
| 020 | Segmentation recovered | PASS | D04 |
| 021 | Comparison methods recovered | PASS | D07: six implementations |
| 022 | Original evidence storage recovered | PASS | D01 B13 |
| 023 | Gap and review infrastructure recovered | PASS | D08 |
| 024 | API contracts recovered | PASS | D13 |
| 025 | Frontend architecture recovered | PASS | D11 |
| 026 | MapLibre and Cesium contracts recovered | PASS | D11: versions and the conflict with thehub-pr's lock |
| 027 | FAWS architecture recovered | PASS | D14: draft proposal in thehub-pr; no schemas |
| 028 | SATIM architecture recovered | BLOCKED | D14: skywatcher-pr not attached; colour convention not found anywhere read |
| 029 | Mucaro execution contracts recovered | PASS | D14 |
| 030 | TheHub governance contracts recovered | PASS | D14 |

### Phase 02 — Internal dataset recovery

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 031 | Existing geographic source assets inventoried | PASS | D02 |
| 032 | Spiderweb Master baseline recovered | BLOCKED | D02: external file, not available |
| 033 | Historical geographic assets recovered | UNVERIFIED | Not located in the repository; not searched beyond registries |
| 034 | Imagery inventories recovered | PARTIAL | D02: provider registrations only; no imagery stored |
| 035 | Elevation inventories recovered | PASS | D02 |
| 036 | Hydrological inventories recovered | PARTIAL | D02: registry counted, contents not examined |
| 037 | Administrative geography recovered | PARTIAL | D02: manifests only; geometry not present |
| 038 | Other Federation geographic datasets recovered | BLOCKED | D02: five repositories not attached |
| 039 | Duplicate and superseded assets reconciled | PARTIAL | D02: three cases found and recorded; not exhaustive |
| 040 | Internal dataset denominator established | OPEN | D02: cannot be closed from this environment |

### Phase 03 — Architecture reconciliation

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 041 | Backend responsibilities reconciled | PASS | D12 |
| 042 | Frontend responsibilities reconciled | PASS | D11 |
| 043 | Reusable components identified | PASS | D11, D12 |
| 044 | Missing capabilities identified | PASS | D11, D12 |
| 045 | Duplicate registries eliminated | OPEN | Identified; an index is queued (D18 A01). None removed. |
| 046 | Redundant processing eliminated | OPEN | Identified. This work adds a second execution mechanism by owner decision (D14). |
| 047 | Repository authority boundaries established | PARTIAL | D14; the workbench surface conflicts with an existing rule until amended |
| 048 | Renderer version locks reconciled | OPEN | Conflict recorded (D11); not reconciled |
| 049 | Storage architecture qualified | PARTIAL | Artifact root, atomic rename and one receipt per content hash are tested; a store for multi-gigabyte rasters is not |
| 050 | Architecture reuse matrix | PASS | D11, D12 |

### Phase 04 — Contract preparation

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 051 | Scope and denominators frozen | PARTIAL | Frozen for the pilot (D17); not for the programme |
| 052 | Segmentation policy qualified | PARTIAL | D04; Grid V2 is a release candidate |
| 053 | Source identity contract qualified | PARTIAL | D03 candidate |
| 054 | Dataset version contract qualified | OPEN | Identifier form only |
| 055 | Native asset identity contract qualified | PARTIAL | Schema, 28 instances and tests; archives and replicas unspecified |
| 056 | Footprint contract qualified | PASS | D03, D04; `tests/test_geo_sar_pilot.py` |
| 057 | Acquisition requirement contract qualified | PARTIAL | D06; computed for the pilot |
| 058 | Comparison method contract qualified | PARTIAL | D07; registry exists, nothing qualified |
| 059 | Observation and annotation contract qualified | BLOCKED | Depends on 028 |
| 060 | Gap contract qualified | PARTIAL | D08; local candidate, six instances |
| 061 | Segment review lifecycle qualified | OPEN | Not specified beyond cell states (D09) |
| 062 | Independent coverage accounting qualified | PARTIAL | D08 table; computed by hand for the pilot |
| 063 | API contracts qualified | PARTIAL | D13 specification only |
| 064 | Persistent execution contract qualified | PASS | D16: implemented and tested for local steps |

### Phase 05 — GUI preparation

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 065 | Existing viewer components recovered | PASS | D11 |
| 066 | Shared geographic context qualified | PARTIAL | D10 specification |
| 067 | Reusable comparison panel qualified | PARTIAL | D10 specification |
| 068 | Cascading selectors qualified | PARTIAL | D10 specification |
| 069 | Acquisition-aware selectors qualified | PARTIAL | D10 specification |
| 070 | Synchronised viewports qualified | PARTIAL | D10 specification; prerequisite defect open |
| 071 | Independent panel state qualified | PARTIAL | D10 specification |
| 072 | Native evidence inspection qualified | PARTIAL | D10 specification |
| 073 | Comparison results table qualified | PARTIAL | D10 specification |
| 074 | Logical mosaic matrix qualified | PARTIAL | D09 specification |
| 075 | Segment navigation qualified | PARTIAL | D10 specification |
| 076 | SATIM annotation integration qualified | BLOCKED | Depends on 028 |
| 077 | Desktop layout qualified | PARTIAL | D10 specification |
| 078 | Tablet layout qualified | PARTIAL | D10 specification |
| 079 | Mobile layout qualified | PARTIAL | D10 specification |
| 080 | GUI acceptance specification frozen | PARTIAL | D10 acceptance list; surface decision not yet ratified |

### Phase 06 — Pilot preparation

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 081 | Representative public test extent selected | PASS | D17 |
| 082 | Pilot denominator frozen | PASS | D17: 42 segments, 28 files, catalogue closed |
| 083 | Two dataset versions identified | PASS | D17 |
| 084 | Exact original filenames identified | PASS | `registry/geo_sar/pilot_001_asset_ledger.json` |
| 085 | Native footprints verified | PASS | Read from file headers; 28 of 28 |
| 086 | Existing local evidence reconciled | PASS | 28 of 28 agree with the older registry; 3 earlier acquisition receipts matched by size and object tag |
| 087 | Missing acquisition requirements established | PASS | D06: all 28, with sizes |
| 088 | Comparison eligibility fixtures | PASS | D17 |
| 089 | Known discrepancy fixtures | PASS | D17: pilot gap 006 |
| 090 | Known missing-data fixtures | PASS | D17: pilot gaps 001 to 005 |
| 091 | False-positive rejection fixtures | PASS | D17: four cases |
| 092 | Duplicate acquisition fixtures | PASS | D17; D16 test 05 |
| 093 | Interrupted retrieval fixtures | PASS | D16 tests 03, 04, 08; local file only |
| 094 | Recovery and authorisation fixtures | PASS | D16 test 06 |
| 095 | Pilot acceptance requirements frozen | PASS | D17: eight items |

### Phase 07 — Implementation admission

| Gate | | State | Evidence or reason |
|---|---|---|---|
| 096 | Architecture reuse matrix generated | PASS | D11, D12 |
| 097 | Internal dataset inventory generated | PARTIAL | D02, with unverified parts |
| 098 | Source acquisition specification generated | PASS | D05, D06 |
| 099 | Canonical data contract specification generated | PARTIAL | D03, D07, D08; version and review contracts missing |
| 100 | Frontend component specification generated | PASS | D10 |
| 101 | Backend module specification generated | PASS | D12, D13 |
| 102 | API contract specification generated | PASS | D13 |
| 103 | Security qualification requirements generated | PASS | D15 |
| 104 | Dependency-directed implementation queue generated | PASS | D18 |
| 105 | Persistent execution durability verified | PASS | D16: ten of ten for local steps. Certification WITHHELD. |
| 106 | Exact implementation starting head established | PASS | D19 below |
| 107 | Mandatory preparation gates reconciled | PASS | This table |
| 108 | Preparation readiness calculated | PASS | Counts below; no single score is given |
| 109 | Preparation evidence dossier generated | PASS | This file |
| 110 | Implementation authorisation requested | WITHHELD | Not requested: the gates above are not all satisfied |

## VECTOR

Active vector: FED-GEO-SAR-001 preparation. **Not exhausted.** It stays open
on the blocked and open gates below. No other vector was opened.

Leads logged without switching:

- The 2018 survey's lots: what part of a tile each fills, and why sizes
  differ fivefold.
- Why the 2024 survey reads lower than the 2018 survey at every site the
  elevation lane compared (its own two explanations are unseparated).
- Whether Grid V2 covers the maritime extent.
- The unmerged area-of-interest workbench branch.

## GAPS

### Blocked on access (owner action)

| Gate | Needs |
|---|---|
| 028, 059, 076 | skywatcher-pr attached, to recover the SATIM annotation contract and colour convention |
| 032 | The Spiderweb Master GeoPackage |
| 038 | The other four producer repositories |

### Open by decision or by work

| Gate | What is open |
|---|---|
| 009 | Preparation did not run under a durable job |
| 040 | Internal dataset denominator cannot be closed here |
| 045, 046 | Duplicate registries and redundant processing are identified, not removed; one mechanism was added |
| 048 | Renderer versions differ from thehub-pr's lock |
| 054, 061 | Dataset version contract and segment review lifecycle are not written |

### Findings that change the plan

1. **No Federation route can admit an acquisition job.** thehub-pr's executor
   admits code changes only; mucaro-ai's federation route is unavailable. The
   local ledger fills the gap and is not governed.
2. **Three things the directive assumes exist were not found:** a Federation
   gap taxonomy, a qualification receipt schema, and the SATIM colour
   convention.
3. **The workbench surface conflicts with a standing rule** that this
   repository's frontend is diagnostic only.
4. **Two unguarded archive extractions and several unrestricted fetch paths**
   exist in acquisition code today (D15). They precede this work and must be
   fixed before acquisition is widened.
5. **The pilot's data is not as the older registry described it.** One
   registered version is several lots; per-file alternates are not
   alternates file to file (D17).
6. **LOCKSTEP does not check what its bindings say it requires** (D14).
7. **The elevation lane had already compared the pilot's two versions** at
   one tile position two days earlier, with hashes for three pilot files.
   That evidence was reconciled into the ledger. It shortens the pilot: the
   method exists and one result exists; what is missing is acquisition,
   segment binding and qualification.

### Contradictions preserved, not resolved

- Directive: no duplicate infrastructure. Owner decision: a local ledger.
  Both recorded; D14 states the cost.
- Directive: workbench in this repository. Standing rule: diagnostic only.
  Recorded in the decision record; unresolved until thehub-pr amends it.
- Older registry: zone 20N files are complete alternates. Measured: they are
  not, file to file. The older registry was left unchanged.

## READINESS

| Area | State | Basis |
|---|---|---|
| Capability reconciliation | PASS | D01, D11, D12 |
| Pilot preparation | PASS | D17: 15 of 15 gates |
| Persistent execution, local steps | PASS | D16 |
| AFK continuity certification | WITHHELD | D16, "Not covered" |
| Contracts | PARTIAL | Candidates; two not written |
| Interface | PARTIAL | Specified; nothing prototyped |
| Dataset denominator | UNVERIFIED | D02 |
| Federation governance binding | BLOCKED | D14 |
| Programme implementation admission | WITHHELD | Gate 110 |

What can proceed now without further access: D18 stage 0 items Q01 to Q03 and
Q06, stage A items A01, A02 and A04, stage B items B01 to B05, and stage D
items D01 and D02.

What needs the owner: the five decisions at the end of D18.
