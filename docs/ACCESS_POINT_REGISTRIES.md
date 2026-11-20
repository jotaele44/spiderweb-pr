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
product is held for them, and no record cites one.

The Inland registry also holds the first two sources whose exact bytes were
held: two 1 m LiDAR elevation tiles, each registered with the SHA-256 of the
full file (see "Real-survey processing"). They are grids, so they are
registered but are not direct measurements, and no record cites them either.

The Off-Shore registry holds its first survey product whose exact bytes were
held: one gridded multibeam survey file, `W00247_MB_VR_MLLW_3of4.bag`,
registered with the SHA-256 of the full file under the lineage of the survey
it belongs to (see "The off-shore run of 2026-11-18"). It is a grid, so it is
registered but is not a direct measurement, and no record cites it.

The Inland registry also holds three published reference maps supplied by the repository owner,
each by the hash of its exact bytes: the USGS outlines of sinkholes deeper than
30 m, the USGS areas of sinkholes 5 to 30 m deep, and the Planning Board's
northern karst limit (see "Reference maps and the comparison with them"). They
are published interpretations, not measurements, and no record cites them.

The five provisional records cannot advance until the screenshots they came
from are registered with their exact bytes and hash.

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

## Real-survey processing

One real survey product has been taken through the whole path: fetched under an
explicit grant, hashed, bound to the vertical reference it states, cut to a
window, searched for closed basins, and compared with a second, independent
survey of the same ground.

**Fetching a product** is separate from discovery and narrower
(`spiderweb/access_points/products.py`). A product is fetched only by its exact
address, under its own grant
(`SPIDERWEB_ACCESS_POINT_ACQUISITION=product:<files>:<bytes>:<who granted it>`)
that bounds both the number of files and the total bytes. The size is checked
before any byte is read: a response with no declared length, a length over the
remaining ceiling, or a length that disagrees with the catalogue is refused. The
file is hashed as it is written. A metadata grant cannot be spent on a product,
nor a product grant on a catalogue query. There is no bulk path.

**A run is declared** in `configs/access_point_survey_runs.yaml` and has two
halves. `--extract` needs the held products and writes the small pieces that are
committed: lossless window subsets, the download manifests, and a summary of a
wider window. The default and `--check` of
`scripts/process_access_point_survey.py` use only what is committed and must
reproduce the sealed report exactly. The window centre is the point the registry
already holds for the target record; a run that states a position is refused.

### The run of 2026-11-17

Two tiles of the USGS 1 m elevation model that cover the registered point of
`INAP-PR-000003`, fetched under an explicit owner grant of two named files and
800 MB (716 MB used). They are not in the repository; their hashes are.

| | 2018 survey | 2024 survey | Class |
|---|---|---|---|
| Product | `USGS_1m_x72y204_PR_PRVI_F_2018.tif`, 332,533,267 bytes | `USGS_1M_19_x72y204_PR_PuertoRicoUSVI_D24.tif`, 383,650,591 bytes | FACT |
| Surveyed | 2018-04-17 to 2019-04-19 | 2023-12-27 to 2025-03-20 | FACT |
| Vertical datum as stated | NAVD88, in one programme-wide sentence of the abstract | the same sentence | FACT |
| Can that datum be true there? | No: NAVD88 is not realised in Puerto Rico | No | COMPUTED |
| Published vertical uncertainty | 7.2 cm RMSE (project figure, from the elevation inventory) | none published | FACT |
| Closed basins ≥ 1 m deep and ≥ 100 m² in the 1 km window | 17, deepest 3.0 m | 19, deepest 3.1 m | COMPUTED |
| Strongest tier the shape evidence reaches | SUPPORTING | CANDIDATE (uncertainty unknown) | COMPUTED |
| Rung a scratch registry would give them | FEATURE | ANOMALY | COMPUTED |

What the two surveys say together [COMPUTED]:

- 13 of the 17 basins in the 2018 survey are also in the 2024 survey (bounding
  boxes overlapping by at least half); their deepest points lie a median 2.2 m
  apart. Four appear only in 2018 and six only in 2024, all near the 1 m depth
  threshold.
- Over the million cells of the window the two surfaces differ by a median of
  1 cm (median absolute difference 7.7 cm; 89% of cells within 0.3 m). So the
  two products share a vertical reference in practice, whatever it is called.
- The registered point of `INAP-PR-000003` falls inside the bounding box of a
  shallow basin in both surveys (1.1 m and 1.3 m deep, about 4,200 m²), 44 to
  75 m from its deepest point.
- In a wider 3 km window, read from the held tiles, the nearest basin deeper
  than 10 m is about 1.3 km from the point, and the deepest closed basin is
  12 m (2018, which covers 77% of that window) or 16.5 m (2024).

What this does and does not show:

| Statement | Class |
|---|---|
| There is a shallow closed depression at the registered point, seen by two independent surveys | COMPUTED |
| No closed basin deeper than about 3 m lies within 500 m of the registered point | COMPUTED |
| The legacy record calls this place a sinkhole of a cave system. Nothing in either surface shows an opening, a shaft or a cave; a 1 m elevation grid cannot | FACT about the method |
| Whether the legacy coordinate is where the record's author meant is not established; its accuracy was never stated | UNKNOWN |
| Thresholds (1 m, 100 m², half-overlap) are working values, not calibrated | FACT |

No feature, observation or status changed. A detection is a shape. It was not
attached to the record: distance is discovery, not identity.

### The off-shore run of 2026-11-18

The first seabed survey taken through the same path
(`spiderweb/access_points/bathymetry_run.py`,
`scripts/process_access_point_seabed.py`; declared under `seabed_runs` in
`configs/access_point_survey_runs.yaml`). It has the same two halves as an
inland run, and differs in two ways, both on purpose:

- **It names no target record and states no position.** No off-shore record
  holds one. The only place it names is a declared search area, and a run that
  states a position, a box or a target record is refused.
- **The vertical uncertainty is the product's own, cell by cell**, not one
  figure for a whole project.

The product is file 3 of 4 of NOS hydrographic survey W00247, the one grid of
that survey which the August 2026 receipt
(`evidence/marine/w00247_bag_v0_1/w00247_bag_receipt.json`) found inside the
Guayama–Punta Tuna search area. One metadata request froze the survey's landing
page; one file was fetched under an explicit grant of one file and 8 MB
(6.9 MB used). The file is not in the repository; its hash, its download
manifest and a 58 KB lossless copy of its base grid are.

| | W00247, file 3 of 4 | Class |
|---|---|---|
| Product | `W00247_MB_VR_MLLW_3of4.bag`, 6,935,533 bytes, SHA-256 `b0daca03…65e8` | FACT |
| Same bytes as the August receipt | Yes: hash, size, covered cells, elevation range and uncertainty range all agree | COMPUTED |
| Surveyed | 2013 (survey inventory); the grid file is dated 2021-12-07 | FACT |
| Grid read | Base grid only: 256 × 256 cells of 64 m, 7,910 with data (12%) | FACT |
| Not read | The file's finer refinement grids (2.4 to 32 m) | FACT |
| Seabed elevation | −1,026.3 to −58.8 m, median −217.2 m | COMPUTED |
| Vertical datum as stated | MLLW, in a structured metadata element and in the coordinate system's name | FACT |
| Can that datum be checked for the region? | Not assessed: a tidal datum has no regional extent to test against. It is never called plausible, so the surface is not joinable to a land surface | COMPUTED |
| Sign | The coordinate system is named as a depth; the stored values are elevations (all negative). Used as stored, not re-signed | FACT |
| Published uncertainty, per cell | 0.18 to 17.6 m, median 2.0 m, 90th percentile 5.6 m | FACT |
| Covered extent against the search area | Fully within. The search area is an analyst's box, not a position | COMPUTED |
| Closed depressions ≥ 2 m deep and ≥ 4 cells | 3; none nested | COMPUTED |

The three depressions [COMPUTED]:

| Depth | Area (lower bound) | Depth uncertainty | Depth ÷ uncertainty | Tier reached | Floor |
|---|---|---|---|---|---|
| 6.5 m | 0.66 km² | 2.6 m | 2.5 | CANDIDATE (below the significance floor of 3) | −78.3 m |
| 4.8 m | 0.67 km² | 1.1 m | 4.5 | SUPPORTING | −78.5 m |
| 2.8 m | 0.05 km² | 0.7 m | 4.1 | SUPPORTING | −78.4 m |

All three are broad and nearly flat: depth is about one hundredth of their
width or less, mean wall slopes are 1 to 1.6 degrees, and 75 to 93% of each is
flat floor. They lie within about 1.5 km of one another on the shallow edge of
the survey, with floors at the same level to within 0.2 m and spill levels 2 m
apart. None meets the rule for a steep-walled pit. Each was classed as a
seafloor depression, which is a shape.

**What the survey cannot show** [COMPUTED]. A cell counts as part of a
depression only where the water above it is deeper than the uncertainty of a
difference of two of its heights. Over 4,426 of the 7,910 covered cells (56%)
that floor is above the 2 m minimum depth, so a 2 m depression there could not
be reported; the median floor is 2.8 m and the highest 24.8 m. **Over more than
half of this survey, no detection is not no depression.** The report carries
its own check: with the uncertainty ignored the surface shows four closed lows,
the three reported and one more (2.1 m deep, four cells) that the rule
withheld. So the three are not an effect of the rule.

| Statement | Class |
|---|---|
| Three closed seabed depressions 2.8 to 6.5 m deep exist in the 64 m base grid of this survey | COMPUTED |
| Two of them exceed their own uncertainty by a factor of four; one does not reach three | COMPUTED |
| A scratch registry would file all three as CANDIDATE: one at the ANOMALY rung, two at FEATURE | COMPUTED |
| Whether they are landforms, sediment lows or gridding artefacts is not established: one survey, one epoch, base grid only | UNKNOWN |
| Nothing in a 64 m grid can show an opening, a shaft or a cave | FACT about the method |
| The survey lying inside the search area places no seed. No off-shore seed gained a coordinate | FACT |
| Thresholds (2 m, four cells) are working values, not calibrated | FACT |

No feature, observation or status changed. The off-shore run has its own
pointer (`CURRENT_SEABED.json`), so the inland pointer and report are
byte-identical to before.

### The same file read from its finer grids (2026-11-19)

The survey file carries, under each of its 7,910 covered base cells, one finer
grid with its own node spacing: 2.4 to 32 m, median 8.7 m. Two further runs read
those grids from the file already held — **no download, no network request** —
resampled to 8 m cells (`resolution_m: 8`):

- `2026-11-19-offshore-8m` keeps the base-grid run's thresholds (2 m, 16,384 m²),
  so only the resolution changes.
- `2026-11-19-offshore-8m-small` lowers the area floor to 1,024 m² (16 cells of
  8 m). The floor was declared before the run and not tuned afterwards.

Both runs share one committed 8 m subset (2.4 MB) and a 10 KB grid of the
finer-grid node spacing. They reuse the base-grid run's frozen landing page and
download manifest. The seabed pointer still names the base-grid run, and the
registry is unchanged.

**How a cell is filled** [FACT, checked]. GDAL's resampled mode puts in each
8 m cell the **mean elevation** of the finer-grid nodes inside it and the
**largest** of their uncertainties. A cell with no node stays empty. Nothing is
interpolated. The plan expected the mean for both bands; the check below showed
otherwise, and the largest is the cautious choice. At extract time, every cell
was recomputed from all 809,925 nodes: all 319,157 cells agree to 1 mm, and
cells with no node are empty in both.

| | Base grid (V9) | Finer grids at 8 m | Class |
|---|---|---|---|
| Covered cells | 7,910 of 64 m | 319,157 of 8 m | COMPUTED |
| Cells with no node, inside covered base cells | — | 187,087 of 506,240 (37%) | COMPUTED |
| Median cell uncertainty | 2.0 m | 0.48 m | COMPUTED |
| Covered cells where a 2 m depression cannot be reported | 56% | 32% | COMPUTED |
| Closed depressions at the V9 thresholds | 3 | 8 (2 nested) | COMPUTED |
| Of these SUPPORTING | 2 | 2 | COMPUTED |

An empty cell is an outlet, so empty ground can lose depressions but never gain
one. Where a finer grid's nodes are further apart than 8 m, some cells receive
no node.

**Do the V9 depressions persist?** The rule was fixed before the runs: SPLIT if
two or more finer outer depressions have their deepest point inside the earlier
outline's box; otherwise PERSISTED if a finer deepest point lies within one base
cell (64 m) and the depths agree within the combined uncertainty. **All three
persisted** [COMPUTED]:

| V9 (64 m) | At 8 m | Distance between deepest points | Tier at 8 m |
|---|---|---|---|
| 6.5 m, CANDIDATE | 7.1 m | 6 m | CANDIDATE |
| 4.8 m, SUPPORTING | 5.3 m, with a 3.3 m basin nested inside | 17 m | CANDIDATE |
| 2.8 m, SUPPORTING | 4.0 m | 13 m | SUPPORTING |

The 4.8 m depression falls to CANDIDATE at 8 m: its depth uncertainty is now
the largest node uncertainty over many more cells, so it no longer clears three
times its uncertainty. Beside the 2.8 m one, 200 m east and outside its V9
outline, a second depression 4.6 m deep appears (SUPPORTING). Both readings
come from the same soundings, so persistence is a consistency check, not
replication.

**The small-area run** finds two depressions more. One is 3.7 m deep and
14,600 m² (SUPPORTING). The other is about 15 m deep, about 2,900 m² and has
13° walls, at the shelf edge (floor −101.5 m). It is smaller than one base cell
and so carries the possible-artefact flag; under the stated rule every
depression smaller than one base cell does. In the finer-grid nodes it is a
narrow west–east line about 160 m long, and only 13 nodes lie more than 10 m
below its rim [COMPUTED from the held file]. With the uncertainty ignored, the
small-area run sees two further closed lows, 8.9 and 6.4 m deep, that the
uncertainty rule withheld.

**Is it a seam between finer grids? The declared test says no.** One
south-to-north profile through its deepest point showed the north side about
8 m lower than the south side would continue, and it was first read as a seam.
A seam test was then written and fixed before it was applied to any detection
(`survey.seam_test`; the rule is in `docs/ACCESS_POINT_SCIENTIFIC_METHOD.md`,
section 3). It calls a depression SEAM_LIKELY only if it is narrow and
grid-aligned, shows a level step across its axis along most of its length, and
that step continues past both ends. Applied to every outer depression in both
8 m runs [COMPUTED]:

| Depression | Width (cells) | Angle from grid axis | Step significant along its length | Step continuing past its ends | Classification |
|---|---|---|---|---|---|
| 15.1 m, 2,944 m² | 2.5 (limit 2) | 5.3° (limit 5°) | 40% (needs 80%) | 10% (needs 50%) | NOT_SEAM_LIKE |
| The other seven outer depressions | 9 to 51 | 1.6° to 26° | 26% to 67% | 0% to 7% | NOT_SEAM_LIKE |

The 8 m step is real at the deepest column but is not consistent along the
object, so the seam reading over-generalised from one profile and is
withdrawn. The test itself does find a planted seam (tested on synthetic
surfaces), so its answer here is not a blind spot of the test. The object
stays a flagged, unexplained small depression: neither a seam nor a pit is
established. The shape of the rule was suggested by that one profile, which is
stated in the report.

| Statement | Class |
|---|---|
| The finer grids were read exactly as the file holds them (every cell recomputed from the nodes) | COMPUTED |
| The three base-grid depressions are present in the finer grids, in the same places | COMPUTED |
| Finer reading of the same soundings is not a second survey | FACT about the method |
| The 15 m linear object is a seam between finer grids | Not supported: the declared seam test says NOT_SEAM_LIKE |
| What the 15 m linear object is | UNKNOWN |
| Whether any of the depressions is a landform rather than a sediment low or a gridding effect | UNKNOWN |

No feature, observation or status changed, and nothing was registered.

### A search for an independent second survey (2026-11-20)

The depressions above come from one survey. A finer reading of the same file is
not replication; another cruise, another year and other soundings would be. A
declared search (`spiderweb/access_points/replication.py`,
`scripts/search_access_point_replication.py`; `replication_searches` in
`configs/access_point_survey_runs.yaml`) recorded what is available. It made
**two metadata requests and one download**, each under a grant from the
repository owner's in-session decision of 2026-11-20. Its sealed report is
rebuilt from committed evidence.

| Step | Result | Class |
|---|---|---|
| NOS survey H12935 (NOAA Ship Nancy Foster, 7–18 April 2016): the only gridded survey whose catalogue box overlapped the depressions | Fetched under a grant of one file and 40 MB: 37,801,093 bytes, SHA-256 `58ba678b…1df41`, held outside the repository. **Its own grid has no soundings within 11 to 17 km of any depression**; the survey's bounding box is not its coverage | FACT |
| Its coordinate system | The file gives no EPSG code for the horizontal part; matched by its parameters to EPSG:26920 and recorded as matched, not stated | COMPUTED |
| One query of the NCEI multibeam footprint service around the depressions' deepest points | Six cruises; the footprint polygons of RB0604 (2006), NF-14-01T (2014) and NF2202 (2022) contain five to eight of the eight outer depressions | COMPUTED |
| Is a cruise the same acquisition as W00247? | NF-13-02 has the same ship, year and an instrument model in common with W00247, so it is probably the same soundings; the others are independent | INFERENCE |
| What NCEI holds for each independent cruise that crosses the depressions | Raw pings only | FACT (discovery catalogue of 2026-11-16) |
| The one processed grid crossing W00247 (EX1502L3, 50 m) | Its receipt of August 2026 shows nothing shallower than 448 m over W00247's covered cells; the depressions' floors are at 72 to 101 m | FACT |

**Outcome: BLOCKED.** Every independent cruise that crosses the depressions is
held only as raw multibeam pings. A grid made from raw pings needs the cruise's
own sound-speed, tide and attitude corrections. A grid improvised here would not
be evidence, so none was made, and the depressions stay unreplicated. Footprint
polygons are where a cruise ran its sonar, generalised; they are not coverage
of any one point.

## Reference maps and the comparison with them

A reference set is somebody else's map. It is declared in
`configs/access_point_reference_sets.yaml` with the hash of its exact bytes, the
coordinate reference system **bound** to it and where that binding was read, and
the publisher's own statement of positional accuracy
(`spiderweb/access_points/reference.py`). The loader refuses a file whose bytes
differ from the declaration, refuses coordinates that cannot belong to the bound
system, and refuses a shapefile whose projection file names a different one. A
set that is not held is recorded by hash for lineage and never parsed.

| Set | Held | Role | Note |
|---|---|---|---|
| USGS Karst Map: sinkholes deeper than 30 m (1,173 outlines) | Yes, 1.0 MB | Labels | The export declares no coordinate system; bound to EPSG:32161 from the parent database, confirmed by 1,171 of 1,173 outlines falling inside the karst limit |
| USGS Karst Map: areas of sinkholes 5–30 m deep (31 polygons) | Yes, 0.2 MB | Context | Areas, not individual sinkholes |
| PR Planning Board northern karst limit (1 polygon) | Yes, 43 KB | Karst limit | EPSG:6566, from the archive's own projection file. Kept in the repository by the owner's decision of 2026-11-20; no separate licence text came with the layer |
| USGS Karst Map: rock units (805 polygons) | Hash only | Lithology | Used once, from the owner's upload |
| The parent geodatabase; a network link to the government map server | Hash only | Lineage | Not parsed; the link is never fetched |

`scripts/validate_access_point_detector.py` compares the closed-basin detector
with the label set on the held elevation tiles. The result is
**REFERENCE_COMPARED**, never MEASURED: within the map's stated 100 m tolerance,
88% of mapped sinkholes are closed depressions at least 30 m deep in the 2024
survey, against 51% for a displaced control; the detector reports only 32% of
them as separate objects, because it reports the outermost basin of a compound
depression. With the opt-in nested-basin mode that rises to 61% (control 28%),
and 70 of the 73 sinkholes that lay inside a larger basin are reported as their
own object. Nested basins are the detectors' default since 2026-11-18; a second
rule for a single pit under a bowl was measured, did not help, and is off. The figures, their limits and what they do not show are in
`docs/ACCESS_POINT_SCIENTIFIC_METHOD.md`, section 6.

What the maps say about `INAP-PR-000003` [COMPUTED]: its registered point is
inside the karst limit, on ground mapped 90% as chalk and marl; it is not in an
area of sinkholes 5–30 m deep; no mapped sinkhole deeper than 30 m lies in the
surveyed window, and the nearest is 2.6 km away. That agrees with the two
surveys, which found only shallow basins there. Nothing was attached to the
record.

## Export to the federation hub

Authorised by the repository owner on 2026-11-20. The hub (thehub-pr) runs this
repository's `export_canonical` command from `federation.json`, which now passes
`--access-point-registries registry/access_points` to
`scripts/federation_export.py`. The lane
(`spiderweb/access_points/hub_export.py`) reads the two committed registry
documents, refusing one that does not match its content hash, and adds rows to
the existing `sources`, `entities` and `relationships` streams. No stream and
no hub schema or hub code changes. This repository's own producer schema
(`schemas/federation_entity.schema.json`) gains the three new entity types and an
optional `attributes` object; the hub's schemas already accept both.

| What | How it is exported |
|---|---|
| Records with status CANDIDATE, UNDER_REVIEW or VERIFIED | One entity each: `inland_access_point` or `offshore_access_point`, with the feature id, class, status, tier per evidence dimension, ladder rung and the registry document's content hash as attributes. Today: 4 inland and 1 off-shore, all CANDIDATE |
| Identity | `identity_state CANDIDATE`, `identity_scope PRODUCER_LOCAL` on every record: the hub's correlation can never read a record as the same thing as another producer's |
| Class | `epistemic_class INTERPRETIVE`: a record is the registry's interpretation of its sources |
| Position | A `location` only where the record's own observation states a point, as a `REPRESENTATIVE_POINT`. Where the source never declared its coordinate system the method says `LEGACY_REGISTRY_POINT_CRS_ASSUMED` (all five today) |
| Confidence | Required by the hub's schema: 0.3 for CANDIDATE, 0.5 UNDER_REVIEW, 0.9 VERIFIED. An ordering by status, not a probability |
| The registries themselves | One `sources` row and one `access_point_registry` entity per registry; each record links to it with `reported_by` |
| Not exported | PROVISIONAL_DISCOVERY seeds (5 today: no evidence, no coordinates), REJECTED and SUPERSEDED records, survey detections, relationships between records |

The package built with the lane from `exports/real` in production mode passed
the hub's own `validate-package` (hub `origin/main` at 95c6c99) as VALID, with
0 synthetic rows, and the extended command passes the hub's command allow-list.
Nothing reaches the hub until this branch is merged and the hub next runs the
command.

## What this change deliberately does not do

| Not done | Why |
|---|---|
| Register a vector-tile source | The tile publication contract pins the source set; records are served as GeoJSON |
| Add a write or review API | The backend has no authentication |
| Download survey products in bulk | A product is fetched only by its exact address, under a separate grant with a byte ceiling; two elevation tiles and two seabed survey files have been fetched that way |
| Export detections, provisional seeds or relationships to the hub | Only registry records that are candidates or better are exported, each as a candidate identity (see "Export to the federation hub") |
| Correlate records across producers | That is the hub's role; other producers' records are read as context only |
| Change production | Nothing was deployed and no data store was written |

## Impact on consumers

| Consumer | Impact | Reason |
|---|---|---|
| Frontend client | Additive | New panel; existing calls unchanged |
| Desktop launcher | Additive | New routes resolve ahead of the page catch-all (tested) |
| Production app | Additive | Same application object; no new dependency |
| Federation hub | Additive | Candidate access-point records arrive as new entity types in the existing canonical streams once the export command carries the lane; no schema or ingest change (see "Export to the federation hub") |
| Sibling producers | None | No shared contract, schema or identifier rule changed |
| Code using the marine evidence gates | Stricter | A placeholder datum no longer counts as a stated datum; see the scientific method document |

## Security and rollback

The API is read-only, bounds every parameter, never builds a file path from
input, and verifies a registry document before answering from it. Metadata
discovery is denied by default and bounded when granted, per target and per
run; it sends a generic user agent and records no cookie or server header.
Fetching a product needs a separate grant that bounds files and bytes, checks
the size before reading, follows no redirect and accepts only listed hosts.

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
| `products.py` | Fetching a named product inside a byte ceiling; the elevation product catalogue |
| `survey.py`, `survey_run.py` | Reading a real gridded product, binding its stated datum, detection, two-survey replication; the declared, reproducible run |
| `replication.py` | A declared search for an independent second survey: footprints, independence of cruises, what NCEI holds, a candidate product's actual coverage |
| `bathymetry_run.py` | The declared, reproducible run over one gridded seabed survey: no target record, the product's own per-cell uncertainty, and what the survey cannot show; a run may read the file's finer grids at a stated resolution and is compared with an earlier run |
| `reference.py`, `validation.py` | Published reference maps held by hash and read with a bound CRS; the comparison of the detector with a published sinkhole map |
| `federation_context.py` | Read-only context from other producers' packages |
| `seeding.py`, `service.py` | Deterministic registry build; read-only queries |

Vocabularies reused rather than redefined: evidence tiers, the six spatial
states and certification states from `spiderweb/subsurface/evidence.py`; the
non-promotion bases and cardinalities from
`spiderweb/subsurface/svt_contract.py`; sensor, product-stage and coverage
vocabularies and the vertical reference from `gebco/marine_evidence.py`; the
identity default, distance and hashing from `federation/spatial_core.py`; and
the relation verbs from `federation/spatial_relations.py`.
