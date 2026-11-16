# Access points: baseline, capability inventory and cross-repository audit

This is the audit behind the access-point registries: what existed before the
change, what was reused, what was added, what other repositories offer, and
what remains open. Audit date 2026-11-14 and 2026-11-15.

Every row carries a class — FACT (read from a file), COMPUTED (output of a run),
INFERENCE, or UNKNOWN — and, where a decision was made, one of: REUSE_AS_IS,
EXTEND, ADAPT, CONSUME_ONLY, SHARE_THROUGH_CONTRACT, REPLACE_IF_JUSTIFIED,
NOT_APPLICABLE, UNVERIFIED, BLOCKED.

## 1. Frozen baseline

| Repository | Commit at audit | Equal to `origin/main` | Role | Class |
|---|---|---|---|---|
| spiderweb-pr | `cb5aa8eb726ba882b410bcfe0a402799af86ed5a` | yes | Owner of both registries | FACT |
| aguayluz-pr | `e29bfbc55df5e9ea1724fd77837f0ee064ca6d31` | yes | Water, power, environmental infrastructure | FACT |
| thehub-pr | `70b74c7e71a6f380a45fd374332e60eef174e9b8` | yes | Federation hub | FACT |
| skywatcher-pr | `0c0b5c8b075e64797777cdaa5d6518ca7823aaf5` | yes | Aviation, airspace, terrain | FACT |
| moneysweep-pr | `08e1bb2ee7e92c786ba7eb60397fe10703f2ce53` | yes | Public money, contracts, ownership | FACT |

The spiderweb-pr commit is the one the proposal named; nothing had drifted.
Only spiderweb-pr is changed by this work.

Tests before any change, run in an isolated environment (Python 3.12.3,
numpy 2.4.6, scipy 1.17.1, shapely 2.1.2, rasterio 1.5.2):

| Suite | Result | Class |
|---|---|---|
| Core Python suite (the command CI runs) | 2109 passed, 52 skipped, 0 failed | COMPUTED |
| Bathymetry grid suite | 50 passed | COMPUTED |
| Frontend unit tests, type check, lint | 148 passed; clean; clean | COMPUTED |

The 52 skips are optional dependencies, absent local services and
operator-local data. Results after the change are in
`evidence/access_points/certification_report_v1.json`.

## 2. What existed in this repository

| Capability | Where | State before | Decision | Class |
|---|---|---|---|---|
| Distance, bounding boxes, canonical hashing, identity default | `federation/spatial_core.py` | Implemented, tested | REUSE_AS_IS | FACT |
| Typed spatial relations | `federation/spatial_relations.py` | 16 verbs declared, 2 computed, points only | REUSE_AS_IS (verbs reused on export mapping) | FACT |
| Six-state spatial predicate, evidence tiers | `spiderweb/subsurface/evidence.py` | Implemented, tested | REUSE_AS_IS | FACT |
| Non-promotion bases, cardinalities | `spiderweb/subsurface/svt_contract.py` | Implemented | REUSE_AS_IS | FACT |
| Slope, curvature, roughness, rugosity | `gebco/terrain.py` | Implemented, tested; no CRS or datum awareness | REUSE_AS_IS | FACT |
| Marine evidence model: sensors, product stages, coverage, vertical reference, depth comparison | `gebco/marine_evidence.py` | Implemented, tested; three loopholes | EXTEND (hardened) | FACT |
| Frozen HTTP transport with offline injection | `pipeline/marine_sources.py` | Implemented, tested | REUSE_AS_IS (standardised on) | FACT |
| NOAA catalogue and elevation-inventory discovery with count closure | `pipeline/marine_sources.py`, `pipeline/marine_lidar_sources.py` | Implemented, tested offline | REUSE_AS_IS | FACT |
| Inventory-to-observation binding | `pipeline/marine_observation_binding.py` | Marine layers only | REUSE_AS_IS (rule kept; inland rows mapped in the new layer) | FACT |
| Coastal elevation model registry and datum policy | `source_adapters/ncei_coastal_dem/` | Implemented, tested; one loophole | EXTEND (hardened) | FACT |
| Terrain screening score for flat benches | `tools/pr_dem_one_tile_pilot.py` | Detects raised flat patches, not basins; maximum score 45 against thresholds of 50 and 70 | NOT_APPLICABLE (opposite morphology) | FACT |
| Subsurface evidence governance (frozen areas, source denominators, residual states) | `spiderweb/subsurface/` | Implemented, tested; vector only | REUSE_AS_IS (vocabularies) | FACT |
| Read-only backend | `server/backend/main.py` | 23 routes, no versioning, no authentication, no bounding-box query | EXTEND | FACT |
| Map workbench | `server/frontend/src/` | Six modules, MapLibre; Cesium a bare scene | EXTEND | FACT |
| Remote-monitoring backbone | `spiderweb/remote_monitoring/` | Area registry and candidate logic; no scheduler, no change events | NOT_APPLICABLE (satellite scenes; different entity) | FACT |

Absent before this change: closed-basin delineation, sinkhole or seafloor
depression detection, a controlled vertical-datum vocabulary, cross-sections,
coastline versions, a registry of access-point features, typed relationships
with path verification, any spatial query in the API. [FACT]

## 3. Existing marine capability

| Capability | State | Class |
|---|---|---|
| Survey catalogue discovery, paged, count-closed | Implemented, tested offline | FACT |
| Elevation inventory layers (topographic, topobathymetric, bathymetric LiDAR, radar, other surveys) | Implemented, tested offline | FACT |
| Exact-byte freezing of responses with hash re-verification | Implemented, tested | FACT |
| "A failed request is not zero data" | Enforced in code, tested | FACT |
| "Inventory coverage is not a depth measurement" | Enforced in code, tested | FACT |
| "Derived products of one survey are not independent" | Partly enforced before; the rootless case is closed by this change | FACT |
| Gridded survey file reading | Scripts only, untested, not a library | FACT |
| Frozen response bytes in the repository | None; they lived in 30-day workflow artifacts | FACT |

**Guayama–Punta Tuna workflow.** Five committed receipts under
`evidence/marine/`. What they establish, and what is still open:

| Step | Outcome | Class |
|---|---|---|
| v0.1 source denominator | 13 multibeam surveys, 29 sounding surveys, 1 gridded survey, 4 topobathymetric LiDAR projects in the corridor | FACT |
| v0.2 file-level product discovery | BLOCKED: the file endpoint returned HTTP 500 for all 42 surveys | FACT |
| v0.3 alternate product paths | PASS: product links found | FACT |
| v0.5 second sensor | Second independent sensor root: PASS. Vertical datum equivalence: UNRESOLVED_CONTRADICTION. Depth subtraction: BLOCKED. Multisensor confirmation: BLOCKED. Screenshot registration: BLOCKED (no control points) | FACT |

These gates are carried forward unchanged. The registries cite the v0.1
surveys as references and make no feature claim from them.

## 4. Acquisition adapters

At least eleven independent HTTP call sites exist, almost all on the standard
library with a timeout and no retry, rate limit or resume. Two are injectable
for offline tests. [FACT]

**Decision.** No twelfth was added. The shared layer
(`spiderweb/access_points/acquisition.py`) standardises on the existing marine
transport — the only one that separates fetching from freezing and returns the
final address, status, headers, hash and retrieval time — and calls the
existing fetchers. It adds what was missing, once, as wrappers: a default-deny
authorisation gate, a request budget, retry with back-off, a rate limiter, and
an offline replay transport over frozen fixtures.

One discovery path serves both registries, because the elevation inventory
lists terrestrial LiDAR as well as bathymetric surveys.

| Requirement | State | Class |
|---|---|---|
| Explicit geographic query | Implemented | FACT |
| Stable source identifiers; row numbers flagged as unstable | Implemented, tested | FACT |
| Pagination completeness | Reused; failures reported per provider | FACT |
| Retry, rate limit | Implemented, tested | FACT |
| Exact address and hash preservation | Reused | FACT |
| Four dates kept apart (discovered, published, surveyed, retrieved) | Implemented | FACT |
| Licence class recorded | Recorded; not enforced | FACT |
| Offline fixtures | Replay implemented and tested with synthetic payloads; no real frozen responses committed | FACT |
| Planned runs over declared search areas | Implemented (`spiderweb/access_points/discovery.py`): offline plan, per-target and per-run request ceilings, sealed source catalogue, offline replay check | FACT |
| Search areas kept apart from feature positions | Implemented, tested: a corridor that states a position, depth or feature is refused | FACT |
| Data-product download | **Not implemented.** Discovery is metadata only | FACT |
| Temporal query, resume of large downloads | Not implemented | FACT |
| Terrestrial sources beyond the elevation inventory (3DEP tiles, geology, karst inventories, parcels, roads) | Not integrated | FACT |
| Live run | Not executed: the run is prepared (10 targets, 48 first requests, three public catalogue hosts) and waits for an explicit grant from the repository owner | FACT |

## 5. Cross-repository dependency matrix

Rule that governs all of it: producers own their records; this repository
reads exported packages only, keeps foreign identifiers verbatim, and never
correlates across producers — that is the hub's role.

| Repository | What was found | What can be consumed, and how | State | Class |
|---|---|---|---|---|
| aguayluz-pr | 19,757 utility assets, 16,064 located: 126 groundwater wells, 1,085 stream gauges, 11,199 water-quality sites, 5 tide gauges, 95 wastewater plants, 223 reservoirs. No aquifer polygons, hydrostratigraphic units, sinkholes or submarine discharge data. Hydro tracing tested only on synthetic input | Monitoring sites and water assets, as context, from its exported `entities` stream | **BLOCKED**: no exported package is committed at the audited commit. The reader is written and tested on synthetic packages | FACT |
| moneysweep-pr | Exported package: 4,508 sources, 207 entities, 66 relationships. No coordinates anywhere. 8 projects, 4 properties, 3 contracts. No marine or underground construction records | Projects, properties and contracts, as documentary context | **PASS** (verified run): package closes; 15 context records; 0 placeable; furthest lifecycle state documents can show is CONTRACTED | COMPUTED |
| skywatcher-pr | Exported package of 3 observations. Owns the airspace meaning of ILAP. Its terrain helpers return hardcoded depths in places; its change-detection modules score human-supplied signals and read no pixels | Nothing for access points. Package integrity verified | **NOT CONSUMED**; integration preconditions in its own decision record are unmet | COMPUTED |
| thehub-pr | Artifact-only federation; free-string entity types; point-or-municipality geometry only; shared acquisition service (decision record 0006) exists as contracts and offline validators, not as a service | Export contract and identifier rule, when export is authorised | **OPEN**: nothing is exported | FACT |

The verified run is recorded in
`evidence/access_points/cross_repository_verification_v1.json`.

**Non-inference rules**, enforced in `spiderweb/access_points/federation_context.py`
and tested:

- A contract, award, disbursement or ownership record never creates a feature,
  gives it a position, or raises its evidence. It may attach as a function
  *hypothesis*, capped at candidate.
- A municipality name is never turned into a point.
- A producer's coordinates are used only when the producer itself marks them
  as a verified source coordinate.
- Documents can show that something was planned, contracted or funded. Built,
  operational and abandoned require direct observation. "Completed" on a
  contract describes the contract.
- A stream a producer did not export is "not exported", never zero records.
- Fixture and sample directories are refused as evidence.

## 6. Inland Access Points: before and after

| Capability | Before | After | Class |
|---|---|---|---|
| Registry of inland features with evidence per dimension | None | Implemented, tested | FACT |
| Closed-depression delineation | None | Implemented, control-tested | FACT |
| Depression morphology (15 measures) | None | Implemented; circularity checked against analytic shapes | COMPUTED |
| Sinkhole interpretation | Published vector layers only | Proposed only with an evidenced karst context; otherwise "closed depression" | FACT |
| Artificial excavation signature | None | Rectilinear flat-floored cut, as an origin hypothesis | FACT |
| Topographic position, local relief, hillshade | Position index in a pilot tool, mean filter | Implemented, no-data aware, tiled | FACT |
| Vertical datum control for land models | None | Required to construct a surface | FACT |
| Survey seam flagging | None | Grid-aligned seams | FACT |
| Candidate scoring | Uncalibrated score for the opposite morphology | Review-priority score, explicitly not evidence | FACT |
| Identity adjudication | Rules for wells and quarries | General correspondence with cardinalities; no automatic binding | FACT |
| Precision and recall | None | None for real ground; software controls only | FACT |
| Ground classification, bare-earth extraction, contour trees, point clouds | Absent | Absent | FACT |
| Cave entrance, mine, shaft, tunnel detection from data | Absent | Absent: classes exist in the registry; no detector | FACT |

## 7. Off-Shore Access Points: maturity and parity

| Capability | Inland | Off-Shore | Shared or specific | Class |
|---|---|---|---|---|
| Registry, evidence rules, promotion, documents | Tested | Tested | Shared | FACT |
| Surface construction gates | Tested | Tested | Shared | FACT |
| Basin delineation and morphology | Tested | Tested | Shared | FACT |
| Interpretation rules | Closed depression, sinkhole, excavation | Seafloor depression, blue-hole candidate, survey artefact, escarpment | Specific | FACT |
| Seam flagging | Tested | Tested | Shared | FACT |
| Change between surveys | Tested | Tested | Shared | FACT |
| Source discovery | Elevation inventory (3 layers) | Elevation inventory (3 layers), survey catalogues, gridded survey inventory | Shared transport | FACT |
| Reference sources registered | 0 | 47 | — | COMPUTED |
| Candidate records | 4 | 1, plus 5 provisional | — | COMPUTED |
| Submerged karst, cave entrance, landslide, lineament, engineered structure classification | — | Classes exist; no detector | — | FACT |
| Sediment artefacts, multibeam artefact filtering | — | Absent beyond seams | — | FACT |
| Real surveys processed | 0 | 0 | — | FACT |

Neither registry was simplified to match the other: the processing core is
shared and the interpretation rules differ.

## 8. Defects found in existing code

| Defect | Status |
|---|---|
| Placeholder datum strings counted as a stated vertical reference | FIXED in this change |
| A rootless direct observation outranked a rooted one | FIXED in this change |
| A `source_dependent` datum selection passed datum policy | FIXED in this change |
| `schemas/ilap_corridor_candidate.schema.json` rejects the output of the bridge it is indexed for | OPEN, outside this change |
| `scripts/rescore_ilap_clusters.py` emits a field as an object where `schemas/ilap_cluster.schema.json` requires an array | OPEN |
| `tools/pr_dem_batch_runner.py` calls a score-verification script that does not exist | OPEN |
| Two catalogue layers share one pin identifier prefix because class ids are truncated | OPEN |
| A gridded survey receipt reports negative values under a positive-down depth label | OPEN; the new sign check would reject it |
| Inventory binding accepts a layer-local row number as a stable identifier | OPEN in the existing binding; the new layer flags it |
| Three registries of the same coastal elevation products use different datum vocabularies | OPEN |
| The backend has no authentication; three existing routes start or stop subprocesses | OPEN |
| The bathymetry package exists in two repositories with divergent content | OPEN; recorded in `docs/DUPLICATION_REGISTER.md` |

Open items are reported, not fixed, because they lie outside this change and
several touch files with their own owners and tests.
