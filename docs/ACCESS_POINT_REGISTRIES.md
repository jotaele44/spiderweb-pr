# Access-point registries: architecture and contracts

This document describes the two access-point registries, the evidence rules
they enforce, how records relate to one another, the read-only API and the
map workspace. For the names used, see
[`ACCESS_POINT_TERMINOLOGY_DECISION.md`](ACCESS_POINT_TERMINOLOGY_DECISION.md).
For processing methods and the vertical-datum rules, see
[`ACCESS_POINT_SCIENTIFIC_METHOD.md`](ACCESS_POINT_SCIENTIFIC_METHOD.md).

## What this is, in one paragraph

Inland Access Points and Off-Shore Access Points are two independent registries
of candidate geographic features, built on one shared foundation
(`spiderweb/access_points/`). Each record states what is known about a place
and, separately for each kind of claim, how well it is supported. The code
enforces four distinctions that the rest of this document expands on: a mapped
anomaly is not a feature; a feature is not an access point; an access point is
not a passage; and a passage is not connected to anything. Being near something
is a reason to look, never evidence of identity or connection.

## Current contents

Built from committed inputs by `scripts/build_access_point_registries.py`:

| Registry | Records | Status | Where they came from | Class |
|---|---|---|---|---|
| Inland | 4 | CANDIDATE | Crosswalked from `configs/ilap_registry.yaml` (a quarry, a hydro tunnel, a sinkhole, a spring) | COMPUTED |
| Off-Shore | 5 | PROVISIONAL_DISCOVERY | Operator labels `OSAP-SEED-001` to `-005`; **no coordinates, depths or openings recorded** | FACT |
| Off-Shore | 1 | CANDIDATE | Crosswalked from the same legacy file (a coastal discharge node) | COMPUTED |
| Relationships | 0 | — | No inland and off-shore record lie within 2 km of each other | COMPUTED |

No record is VERIFIED. No record's evidence reaches beyond the lowest rung of
the ladder described below.

The registries also hold reference sources listed by the metadata-discovery run
of 2026-11-16 (see "Source discovery runs"): 177 in the Off-Shore registry (40
multibeam surveys, 105 sounding surveys, 25 gridded surveys, 6 topobathymetric
and 1 bathymetric LiDAR project) and 3 terrestrial LiDAR projects in the Inland
registry. All 47 surveys named by the earlier Guayama–Punta Tuna receipt were
listed again and are held once. They are citations, not measurements: no survey
product is held, and no record cites one. The five provisional records cannot
advance until the screenshots they came from are registered with their exact
bytes and hash.

## Six identities, kept apart

| Identity | What it is | Identifier |
|---|---|---|
| Source manifestation | One exact published thing: a file, a service response | `APSRC-…`, from provider, native id, address and content hash |
| Original observation | One record inside one source, kept as the source stated it | `INAP-OBS-…` / `OFAP-OBS-…` |
| Physical feature | The registry's statement that something exists | `INAP-PR-…` / `OFAP-PR-…` |
| Derived geometry | A shape computed from observations by a named method | `APGEO-…` |
| Relationship | A typed, evidenced link between two records | `APREL-…` |
| Historical continuity | Which feature record replaces which | `supersedes` on a feature |

A revised file under the same name is a new source manifestation. Raw source
labels and attributes are stored verbatim on the observation; normalised values
are added beside them, never in place of them.

## Eight evidence dimensions

Each assertion about a feature addresses exactly one question. None answers
another.

`EXISTENCE` · `MORPHOLOGY` · `NATURAL_OR_ARTIFICIAL_ORIGIN` ·
`PHYSICAL_OPENING` · `ACCESSIBILITY` · `FUNCTION` · `CONNECTIVITY` ·
`TEMPORAL_VALIDITY`

Each carries a tier — `UNRESOLVED`, `CANDIDATE`, `SUPPORTING`, `DIRECT` or
`CONTRADICTED` — and a claim class: `FACT`, `COMPUTED`, `BINDING`,
`INFERENCE`, `ASSUMPTION`, `HYPOTHESIS` or `UNKNOWN`.

## How a tier is lowered

Whatever tier an assertion claims, the rules in
`spiderweb/access_points/rules.py` only ever lower it:

| Condition | Ceiling |
|---|---|
| Basis is discovery-only (proximity, name, same category, equal counts, a contract or funding record, a screenshot annotation, …) | CANDIDATE |
| Basis describes shape only, and the dimension is not existence or morphology | CANDIDATE |
| Claim is a hypothesis, an assumption or unknown | CANDIDATE |
| Claim is an inference | SUPPORTING |
| No cited source is at least referenced by a stable identifier | CANDIDATE |
| No cited source is a held, hashed, rooted sensor observation | SUPPORTING |
| A cited source is not in the registry | CANDIDATE |

Worked example. A multibeam survey, held and hashed, shows a steep round basin
25 m deep. An assertion that a feature **exists** there, on that basis, is
worth DIRECT. An assertion that the basin is a **physical opening**, on the
same basis, is worth CANDIDATE: depth and shape describe a basin, and say
nothing about whether it opens into anything.

A contradiction is preserved. If one assertion says a dimension is DIRECT and
another says it is CONTRADICTED, the dimension is CONTRADICTED until someone
adjudicates.

## The ladder

The strongest statement the evidence supports is computed, never stored:

| Rung | Requires |
|---|---|
| ANOMALY | Nothing. Something was noticed. |
| FEATURE | Existence at SUPPORTING or DIRECT |
| OPENING | FEATURE, and a physical opening at DIRECT |
| PASSAGE | OPENING, and accessibility at DIRECT |
| CONNECTION | PASSAGE, and connectivity at DIRECT |

Rungs cannot be skipped: direct evidence of accessibility without a directly
observed opening leaves a record at FEATURE.

## Status and promotion

`PROVISIONAL_DISCOVERY` → `CANDIDATE` → `UNDER_REVIEW` → `VERIFIED`, with
`REJECTED` and `SUPERSEDED` as terminal states.

- A record is PROVISIONAL_DISCOVERY while no source behind it is at least
  referenced by a stable identifier.
- A record becomes VERIFIED only through `AccessPointRegistry.promote`, which
  refuses unless: the evidence reaches OPENING; no dimension is contradicted;
  an observation carries source-backed coordinates; the existence and opening
  assertions were accepted by a named reviewer; and every source they cite is
  registered with its exact bytes.
- **The producer cannot verify its own evidence.** A reviewer whose identity
  equals the registry's producer is refused, and acceptance recorded by the
  producer does not count.
- There is no automatic or bulk promotion anywhere in the package, and no
  write endpoint in the API.

## Registry documents

Each registry is one JSON document under `registry/access_points/`,
conforming to `schemas/access_point_registry.schema.json`. A document carries
the SHA-256 of its own content and closing record counts. Loading re-checks
every rule above, so a document that was edited by hand, truncated, or that
claims a status its evidence does not support does not load. Ingestion is
idempotent: adding an identical record again changes nothing; adding different
content under an existing identifier is refused.

Rebuild with `python scripts/build_access_point_registries.py`; check that the
committed files are current with `--check`. The build is deterministic.

## Relationships between records

Relationships live in a separate ledger
(`registry/access_points/relationships.json`,
`schemas/access_point_relationship_ledger.schema.json`) because they may cross
the two registries.

| Relationship type | What it establishes | Can be verified |
|---|---|---|
| SAME_VERIFIED_PHYSICAL_FEATURE | The two records are one feature | Yes |
| DOCUMENTED_ENGINEERED_CONNECTION | Engineered connectivity only | Yes |
| MEASURED_HYDRAULIC_CONNECTION | Hydraulic connection only | Yes |
| VERIFIED_GEOLOGICAL_CONTINUITY | Geological continuity only | Yes |
| SHARED_GEOLOGICAL_UNIT | Context: same mapped unit | No |
| SPATIAL_ADJACENCY | Context: near each other | No |
| HYPOTHESIZED_CONNECTION | A proposal, of a stated kind | No |
| CONTRADICTORY_RELATIONSHIP | Evidence against a named relationship | No |
| UNRESOLVED_RELATIONSHIP | Not adjudicated | No |

**Four things are loosely called a connection** — geological continuity,
hydraulic connection, engineered connectivity and human accessibility. A
relationship establishes at most one of them. Water reaching a place says
nothing about whether a person can; a shared rock unit says nothing about
whether water flows.

A relationship is verified only if it is of a verifiable type, its evidence is
worth DIRECT, it cites a registered source, it was accepted by a reviewer other
than the producer, and no contradiction is recorded against it.

**Paths.** A path between two records is verified only if every link in it is
verified *and* every link establishes the same kind of connection.

| Path state | Meaning |
|---|---|
| VERIFIED | Every link verified, one kind of connection |
| MIXED_KINDS | Every link verified, but for different kinds — not one connection |
| HYPOTHETICAL | At least one link is not verified |
| UNRESOLVED | At least one link is unadjudicated |
| CONTRADICTED | At least one link has evidence against it |
| NO_PATH | No recorded path |

Records from the older naming schemes (flight tracks, investigation clusters
and so on) may appear in a relationship only as context or conjecture. They can
never be declared the same feature as an access-point record, or verifiably
connected to one.

**Identity.** Whether two records are the same thing is settled by an
authoritative basis accepted by an independent reviewer — never by a name, a
distance, a category or a count. Correspondences keep their cardinality
exactly: one-to-one, one-to-many, many-to-one, many-to-many, unmatched, or
unresolved. A join never copies a record.

## Read-only API

`server/backend/access_points_api.py`, mounted in `server/backend/main.py`.
All routes are `GET`; any other method answers 405.

| Route | Returns |
|---|---|
| `/v1/access-points` | Both registries with file hash and counts |
| `/v1/access-points/vocabulary` | Controlled vocabularies, read from the code |
| `/v1/access-points/{registry}/features` | A page of records as GeoJSON; `bbox`, `status`, `feature_class`, `limit` (1–500), `cursor` |
| `/v1/access-points/{registry}/features/{feature_id}` | One record |
| `/v1/access-points/{registry}/features/{feature_id}/evidence` | Assertions with asserted and effective tiers, sources, and what blocks verification |
| `/v1/access-points/{registry}/sources` | Sources held, by provider and provenance state |
| `/v1/access-points/relationships` | Relationships with the class each may be drawn as |
| `/v1/access-points/paths` | Paths between two records, each with its state |
| `/v1/access-points/controls/cross-section` | A synthetic control section, labelled as such |

`{registry}` is `inland` or `offshore`.

- **Compatibility.** These are the first versioned routes in the backend. No
  existing route, response or parameter changed. [FACT: route inventory test]
- **Errors.** 404 for an unknown registry or record, and for an identifier
  that belongs to the other registry or to an older naming scheme (no data
  crosses that line); 400 for a malformed query or an ambiguous identifier; 422
  for an out-of-range parameter; 503 when a registry document is missing or
  fails verification — for that registry only.
- **Every response** carries a `provenance` block (file path, SHA-256, counts)
  and a `scope` block stating that the result has no identity effect.
- **Records without coordinates** are returned with `geometry: null` and
  counted in `unlocated_count`. Nothing gives them a position.
- **No write, review or promotion endpoint exists.** The backend has no
  authentication of any kind, so a write route would be unguarded. Promotion
  is a library call made by a named reviewer.

## Map workspace

The Spatial module gains an **Access points** group
(`server/frontend/src/spatial/accessPoints/`):

- Separate toggles for the two registries. Each loads, draws and fails on its
  own; one being unavailable never hides the other.
- Status is shown by shape as well as colour: a filled disc for verified, an
  open ring for candidate, a small faint ring for provisional. A halo appears
  only where a horizontal uncertainty is stated; no halo means unknown.
- Records without registered coordinates are listed, not drawn.
- Selecting a record shows the ladder with the reached rung, the eight
  dimensions, each assertion with its asserted and effective tier, what blocks
  verification, and each source with surveyed, published and retrieved dates
  shown separately.
- The Graph module gains a relationship explorer in which every class has its
  own line pattern and text label, so an unverified link cannot be mistaken
  for a verified one.
- A cross-section view draws each surface on its own vertical reference unless
  a datum join is allowed, and leaves unsurveyed stretches blank.

**3D.** The workbench does instantiate Cesium when the 2D/3D control is used,
but that runtime is a bare scene: it has no terrain, no data layers and no
tests, and the shared runtime interface has no way to add a layer. Access-point
layers are therefore 2D only, and the panel says so in 3D mode. [FACT]

**Coverage limit.** The map camera is clamped to a Puerto Rico envelope. A
record far off shore could not be brought into view; none exists yet. [FACT]

## Source discovery runs

A discovery run asks public catalogues which surveys they list for a set of
search boxes, keeps the exact answers, and writes one sealed catalogue of what
it saw. It is planned, bounded and off unless explicitly granted.

**Search areas are not positions.** A run has two kinds of target:

| Target | Where the box comes from | Class |
|---|---|---|
| Analyst corridor | Drawn from a locality name in `configs/access_point_discovery_corridors.yaml`, one per off-shore seed | ASSUMPTION |
| Point box | Computed around a point a registry already holds, with the half-width stated in the same file | COMPUTED |

A corridor says where to look. It never gives a seed a coordinate, a depth or
an extent: the corridor file is refused if an entry states a position, a depth
or a feature, the registry builder does not read it, and no corridor can be
certified. The Guayama corridor is the existing one, unchanged, so a run can be
compared with the August source-denominator receipt.

**Three commands**, all in `scripts/discover_access_point_sources.py`:

| Command | Network | Effect |
|---|---|---|
| no option | None | Prints the plan: every target and the first request each provider would make |
| `--execute --run-id <date>` | Metadata requests only | Writes the run under `evidence/access_points/source_discovery/<date>/` |
| `--verify <date>` | None | Replays the kept bytes and fails if they no longer reproduce the receipts |

A live run needs
`SPIDERWEB_ACCESS_POINT_ACQUISITION=metadata:<requests per target>:<who granted it>`.
That number bounds one target; `--max-total-requests` bounds the run. A provider
stopped by either ceiling is reported NOT_AUTHORIZED, never empty. Requests go
out with a generic user agent, only an allow-list of response headers is kept,
and a redirect is refused.

**What a run writes.** One receipt per target, the exact response bytes, and
`source_catalogue.json`: every source once, the targets and registries that
listed it, the datum string the inventory published (placeholders counted, not
accepted), and review flags for registered points that fall inside a listed
footprint envelope. `CURRENT.json` names the catalogue the registry builder
reads, with its hash. A run directory is never overwritten.

**What a run establishes.** That a catalogue listed a survey for a box on a
date. [FACT] It does not establish that the survey covers a particular place in
the box, what it measured there, or anything about a feature. Sources it adds to
a registry are REFERENCED_ONLY with unknown coverage; registering them changes
no feature, observation, geometry or status (tested). A survey the Guayama
receipt already names is not registered a second time.

**Rebuilding a catalogue.** The receipts and the kept bytes are the record and
are never edited. The catalogue is derived from them, so
`--recatalogue <date>` may rebuild it offline — and refuses if the kept bytes no
longer reproduce every receipt.

### The run of 2026-11-16

Executed under an explicit grant from the repository owner: at most 15 requests
per search box and 150 in total. It used 48. Every one of the 48 provider
queries answered cleanly; 29 returned rows and 19 returned none. 3.15 MB of
responses are kept under
`evidence/access_points/source_discovery/2026-11-16/raw/`, and replaying them
offline reproduces every receipt and the catalogue. [FACT]

| Search box | Basis | Topobathy LiDAR | Bathy LiDAR | Multibeam | Sounding | Gridded (BAG) | Terrestrial LiDAR |
|---|---|---|---|---|---|---|---|
| North-west of Aguadilla (`OSAP-SEED-001`) | Analyst corridor | 4 | 0 | 21 | 9 | 2 | — |
| Desecheo (`OSAP-SEED-002`) | Analyst corridor | 1 | 0 | 17 | 5 | 1 | — |
| South-western shelf (`OSAP-SEED-003`) | Analyst corridor | 4 | 1 | 14 | 38 | 13 | — |
| Guayama–Punta Tuna (`OSAP-SEED-004`) | Analyst corridor | 4 | 0 | 14 | 29 | 4 | — |
| South of Vieques (`OSAP-SEED-005`) | Analyst corridor | 2 | 0 | 13 | 36 | 7 | — |
| Around `OFAP-PR-000006` | Point box | 5 | 0 | 4 | 7 | 1 | — |
| Around `INAP-PR-000001` | Point box | 0 | — | — | — | — | 2 |
| Around `INAP-PR-000002`, `-000003`, `-000004` | Point boxes | 0 | — | — | — | — | 3 each |

The counts are what each catalogue listed for the box [FACT]; 180 distinct
sources once repeats across boxes are removed [COMPUTED]. The "other
bathymetric survey" layer listed nothing in any off-shore box and the IfSAR
layer nothing in any inland box; because those queries ran cleanly, "none
listed" may be said for those layers and those boxes, and for nothing wider.

What the run found beyond the counts:

| Finding | Class |
|---|---|
| The Guayama box lists everything the August receipt named (47 of 47) plus one more multibeam survey (`NF-13-02`) and three more gridded surveys (`F00729`, `H12935`, `H13147`); nothing was withdrawn | COMPUTED |
| Those three gridded surveys were already in the August sounding list, so they read as newly published grids of known surveys, not new surveys | INFERENCE |
| Of the 10 LiDAR projects that carry a vertical-datum field, 8 hold a placeholder ("User Specified" ×6, "Not Provided" ×2). They are counted and not accepted as a datum | FACT |
| The other 2, both terrestrial, say NAVD88. An inventory datum string describes a project; it binds no product. It must be checked against each product's own metadata before any vertical join, the more so because Puerto Rico's own vertical datum is PRVD02 | FACT, with an open check |
| The multibeam catalogue reports file counts and sizes **for the box asked about**, not for the survey. Those values are kept per box (`query_scoped_attributes`) and are not treated as a conflict. Per box they sum to between 5 GB and 64 GB of raw multibeam files | FACT |
| The elevation inventory publishes its metadata and data-access "links" as HTML fragments or as prose ("Will be available from …"). The adapter now keeps the field verbatim and cites only a real address; two projects therefore have no address yet | FACT (defect found by the run, fixed) |
| 18 review flags: registered points that fall inside a listed footprint envelope. Every envelope is project-wide, so a flag says "look here", not "this place was surveyed". No status changed | COMPUTED |

What the run does not show: that any listed survey covers the place a seed
refers to (the seeds have no position); what any survey measured anywhere; or
anything about an opening, a passage or a connection. No data product was
downloaded.

## What this change deliberately does not do

| Not done | Why |
|---|---|
| Export access-point records to the federation hub | External federation activation was not authorised; the export script, its schemas and its golden files are untouched |
| Register a vector-tile source | The tile publication contract pins the source set; records are served as GeoJSON |
| Add a write or review API | The backend has no authentication |
| Download any survey product | Only metadata discovery is implemented, and it is off unless explicitly granted |
| Correlate records across producers | That is the hub's role; other producers' records are read as context only |
| Change production | Nothing was deployed and no data store was written |

## Impact on consumers

| Consumer | Impact | Reason |
|---|---|---|
| Frontend client | Additive | New panel; existing calls unchanged |
| Desktop launcher | Additive | New routes resolve ahead of the page catch-all (tested) |
| Production app | Additive | Same application object; no new dependency |
| Federation hub | None | Nothing new is exported |
| Sibling producers | None | No shared contract, schema or identifier rule changed |
| Code using the marine evidence gates | Stricter | A placeholder datum no longer counts as a stated datum; see the scientific method document |

## Security and rollback

The API is read-only, bounds every parameter, never builds a file path from
input, and verifies a registry document before answering from it. Metadata
discovery is denied by default and bounded when granted, per target and per
run; it sends a generic user agent and records no cookie or server header.

The change is additive. To roll back, revert the branch commits. No database,
external service or sibling repository was modified.

## Module map

| Module | Purpose |
|---|---|
| `namespaces.py` | Names, identifiers, collision rules |
| `vocabulary.py` | Controlled vocabularies (existing ones imported, not copied) |
| `models.py` | Record types and their validation |
| `rules.py` | Tier lowering, the ladder, promotion blockers |
| `registry.py` | The two registries and their documents |
| `identity.py`, `relationships.py` | Correspondence, typed links, paths |
| `vertical.py`, `raster.py`, `detection.py`, `controls.py` | Datum contract, shared surface processing, candidate discovery, synthetic controls |
| `transects.py`, `coastal.py` | Cross-sections; coastline versions |
| `acquisition.py`, `monitoring.py` | Metadata discovery; source change detection |
| `discovery.py` | Planned, bounded discovery runs over declared search areas; the sealed source catalogue; offline replay |
| `federation_context.py` | Read-only context from other producers' packages |
| `seeding.py`, `service.py` | Deterministic registry build; read-only queries |

Vocabularies reused rather than redefined: evidence tiers, the six spatial
states and certification states from `spiderweb/subsurface/evidence.py`; the
non-promotion bases and cardinalities from
`spiderweb/subsurface/svt_contract.py`; sensor, product-stage and coverage
vocabularies and the vertical reference from `gebco/marine_evidence.py`; the
identity default, distance and hashing from `federation/spatial_core.py`; and
the relation verbs from `federation/spatial_relations.py`.
