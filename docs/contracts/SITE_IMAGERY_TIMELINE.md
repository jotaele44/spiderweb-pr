# Site Imagery Timeline Contract

Status: **Implemented offline, on synthetic fixtures. Live acquisition is a fail-closed
stub. Every output is provisional.**
Date: 2026-11-11 (first written 2026-11-05 as a proposal)

## Purpose

Define how spiderweb-pr builds a dated satellite-scene timeline for sites that another
producer registers (first case: Puerto Rico solid-waste sites, a registry proposed for
aguayluz-pr in its ADR-0004), and how that timeline reaches the hub for visual review.

spiderweb-pr owns the imagery observations. It does **not** own the site registry, site
identity, or any claim about why a site changed.

## Status and precedence

**Interim path.** Hub ADR 0006 (Accepted, 2026-07-29) moves satellite-provider network
access, credentials and the imagery cache into thehub-pr. That ADR names thehub-pr and
skywatcher-pr, not this repository, and the hub has contracts for it but no acquisition
runtime yet. Until that runtime ships, acquisition here is repo-internal. Every adapter
that touches a provider lives behind one seam, `spiderweb/site_timeline/adapters.py`, so
replacing it with hub-brokered artifacts later changes one module. Trigger to revisit: the
hub acquisition runtime ships.

**Precedence (this repository's position, pending hub confirmation).** Hub rules take
priority where an activity crosses a repository boundary or yields a federation-level
claim: cross-producer identity equivalence, correlation, aggregation, certification and
promotion of evidence, frozen shared contracts, and the supported viewer. Producer rules
take priority for repo-internal activity: a producer's own records, pipelines and internal
schemas. An activity is cross-repo if its output leaves the repo, it depends on another
repo's records, or it asserts equivalence or correlation between records of two repos.
Where an Accepted hub ADR expressly reaches repo-internal activity, that ADR governs for
the repository it names. The wording matches aguayluz-pr ADR-0004; a producer repository
cannot bind the hub, so it stays a position until the hub confirms it.

## Implementation

| Part | Role |
|---|---|
| `spiderweb/site_timeline/models.py` | Frozen records (`Site`, `SceneRecord`, `EpochRecord`, `TemporalObservation`, `TemporalScore`), enums, guardrail names, confidence ceilings. |
| `spiderweb/site_timeline/epoch.py` | Epoch classification of a before and after pair. |
| `spiderweb/site_timeline/score.py` | Temporal change score (a port of the SATIM scorer) and the resolution rule. |
| `spiderweb/site_timeline/series.py` | Admission to a series, the exclusion ledger, comparison pairs. |
| `spiderweb/site_timeline/adapters.py` | The single acquisition seam: a synthetic adapter and a fail-closed live stub. |
| `spiderweb/site_timeline/metrics.py` | Change metrics: a fixture metric and the first-pass pixel difference. |
| `spiderweb/site_timeline/records.py` | The three separate output objects and their deterministic ids. |
| `spiderweb/site_timeline/timeline.py` | Orchestration, the document, and `validate_document`. |
| `spiderweb/site_timeline/fixtures.py` | Loading of site lists and synthetic scene fixtures. |
| `scripts/build_site_imagery_timeline.py` | Offline command that builds a timeline document. |
| `scripts/federation_export.py` | The export lane, behind `--site-imagery-timeline`. |

The package imports no HTTP client, imaging library or provider at import time, reads no
environment variable, and writes no file. `tests/test_site_timeline_core.py` pins all
three.

## Inputs

A frozen site list, supplied as data. No code is imported from another repository.

| Field | Meaning |
|---|---|
| `external_site_id` | Opaque id minted by the registering producer. Never parsed or interpreted here. |
| `producer_entity_id` | The registering producer's hub entity id (`ent_` plus 32 hex). Carried as data and never derived here. It travels in the exported rows' `attributes`. |
| `name` | Display name. |
| `lat`, `lon` | WGS84 point. Polygons are not supported yet. |
| `geometry_precision_decimals` | Stated coordinate precision. Missing, or 3 or fewer, means a coarse seed. |
| `authority` | Optional label of the registering authority. |

Unknown keys and duplicate site ids are rejected. A coarse seed (roughly 100 m to 1 km of
coordinate uncertainty) gets a wide chip (about 2 km half-width) and a confidence ceiling
of 0.3. A precise point gets a tight chip (about 0.5 km half-width) and a ceiling of 0.6.
Both sizes and both ceilings are uncalibrated heuristics.

Proximity, name similarity and coordinates never establish that two records are the same
site. Equivalence is adjudicated by the hub. A pin in `configs/pin_registry.yaml` is a
discovery seed, not a site record.

## Admission to a timeline series

Only scenes with a provider-stated acquisition time (`acquired_at`, required by
`docs/contracts/SATELLITE_SOURCE_MANIFEST.md`) enter a series. Every scene a run considers
is either admitted or excluded with a reason, and the ledger must close:
`considered = admitted + excluded`.

| Exclusion reason | Meaning |
|---|---|
| `UNDATED_BASEMAP_CAPTURE` | A capture kind other than a provider scene, such as a consumer-map screenshot. Epoch unknown; never part of a series or a change claim. |
| `UNDATED` | No parseable acquisition time. |
| `UNKNOWN_PROVIDER` | No provider, so the epoch cannot be classed. |
| `DUPLICATE_SCENE_ID` | A scene id already admitted. |
| `SITE_OUTSIDE_SCENE_BBOX` | The scene does not cover the site point. |
| `CLOUD_COVER_UNKNOWN` | Unknown cloud cover is never treated as clear. |
| `CLOUD_COVER_ABOVE_CUTOFF` | Above the cutoff, which is inclusive, defaults to 20 percent and is configurable. It is a tunable heuristic, not a measured threshold. |

The exclusions matter because `imagery/manifest.py` stamps the current time on a missing
acquisition date and reports an unknown cloud cover as 0.0. A capture that reached it
unfiltered would acquire a false date and a false clear sky.

## Epoch classes

| Class | Definition | Disposition |
|---|---|---|
| `same_epoch` | Same provider and the same acquisition date | Render consistency only: no change claim, no score. |
| `near_epoch` | Same provider, under 30 days apart | Scored, and always flagged for review. |
| `cross_epoch` | A different provider, or 30 or more days apart | Valid comparison. |
| `unknown_epoch` | A date or provider is missing, or the capture is not a provider scene | No change claim, no score. Never promoted. |

These follow skywatcher-pr's SATIM mixed-epoch validation spec and are re-implemented
here, not imported, because this repository forbids cross-repo imports. The 30-day
`near_epoch` window is this repository's own uncalibrated heuristic, not taken from the
spec. The existing score-delta tool in `earthgpt/temporal_epoch_compare.py` is not
extended: it compares scores between pipeline snapshots and carries no epoch provenance.

A series produces consecutive pairs and, with three or more scenes, a baseline-to-latest
pair.

## Change claims

Allowed: **visible change between two dated epochs**, nothing more.

- Temporal classes: `STABLE`, `PROBABLE_CHANGE`, `CONFIRMED_VISIBLE_CHANGE`,
  `ARTIFACT_DRIVEN_CHANGE`, `INSUFFICIENT_EPOCH_ALIGNMENT`. `STABLE` means only that the
  score fell below the thresholds. It never asserts absence of change.
- Only coarse change classes (`EXPANSION`, `CONTRACTION`, `SURFACE_COVER_CHANGE`) are
  allowed when the imagery is coarser than 5 m or unknown, **or when the site geometry is
  coarse**. Finer classes are dropped and the drop is recorded as a review reason.
  Sentinel-2 at 10 m therefore supports no per-feature claim.
- The score is a port of the SATIM `score_temporal_change`. Its thresholds and weights
  are copied from the spec and are uncalibrated heuristics. The port is pinned to the
  original by 16 cases in `tests/test_site_timeline_score.py`; that shows the two agree,
  not that either is accurate.
- Score inputs are derived by stated heuristics: overlap is the share of the site chip
  covered by both scenes; registration is the lower scene `geometric_confidence`; scale is
  the finer resolution over the coarser (0.5 when unknown); view angle is 1.0 for the same
  platform and instrument and 0.7 otherwise, because view geometry is not measured;
  artifact confidence is the higher cloud cover as a fraction. Contradiction confidence is
  0.0 because no contradiction source is wired.
- The pixel-difference metric in `imagery/compare.py` is a first-pass, uncalibrated
  measurement, labelled so in the record (`calibrated: false`). It can only speak to
  `SURFACE_COVER_CHANGE`.
- Each change record's confidence is the adjusted change score capped at the site's
  ceiling. It is a bounded visible-change score, not a calibrated probability.

Forbidden: any causal inference (why a site changed), any statement about legality,
operator conduct or intent, any identity claim from proximity, and any change claim that
spans an unknown epoch. A pair that is artifact-driven or poorly aligned is classed as
such and flagged for review. Before and after provenance stay separate, and an original
epoch record is never rewritten: records are frozen. A change record's `result` holds a
closed set of keys, so cause, owner and purpose fields cannot appear.

## Outputs

Three separate objects per scene or comparison. They may reference one another and are
never collapsed into one mutable manifest (hub ADR 0006, object separation).

1. **Acquisition record** (`spiderweb.site_timeline.acquisition_record.v1`), carrying the
   facts of the hub's `acquisition_receipt.v1` contract: provider, requested and completed
   times, outcome, a SHA-256 request digest, artifact ids and classification. It is
   **not** a hub receipt and says so (`hub_receipt: false`): the hub schema requires an
   `audit_event_id` that only a hub acquisition runtime can issue. Synthetic records are
   classified `TEST_ONLY`.
2. **Source artifact reference** (`spiderweb.site_timeline.artifact_ref.v1`): the scene
   metadata and its content address, `sha256:` plus the pixel hash. No pixels and no path.
   Pixels are fetched in memory and never written by this package; a future live adapter's
   cache must be git-ignored. Provider licensing varies.
3. **Provisional change record**, conforming to the hub's `satim_provisional_signal.v1`
   contract: method, method version, parameters, result, confidence, `provisional: true`
   and a review status of `UNREVIEWED` or `NEEDS_REVIEW`. The hub schema allows no extra
   fields, so site, epoch and score context sit inside `result`. A pipeline never sets
   `APPROVED`.

Ids are deterministic digests of their inputs. A run reads no clock: the caller supplies
the timestamp.

The command line produces one JSON document (`spiderweb.site_imagery_timeline.v1`) that
carries the guardrails, the prohibited outputs, an interim-acquisition note and, per
site, the ledger, exclusions, epochs, acquisitions, artifacts and comparisons.
`validate_document` checks it and is the gate for both the command and the export. It does
not trust labels a document carries about itself:

- The epoch class of every comparison is recomputed from the scenes it references, so a
  same-date pair cannot keep a change claim and a near-epoch pair cannot skip review.
- The `synthetic` flag must agree across the document, its artifacts, its acquisition
  records and its change records, and an acquisition is classified `TEST_ONLY` exactly when
  it is synthetic. A flag cleared on some records but not others is rejected, so test data
  cannot reach a production export.
- The epoch records, acquisition records and each change record's before and after
  references must describe the artifacts they name, and scene ids are unique within a site.
  Artifact ids are content hashes, so two scenes with identical pixels share one; scenes are
  therefore identified by scene id.

### Hub rows

The hub receives rows in the `federation_source`, `federation_entity` and
`federation_observation` streams, following hub ADR 0008 and the PPP geometry lane in
`scripts/federation_export.py` (this repository already publishes geometry as observation
rows naming another producer's entity). The lane is omitted unless
`--site-imagery-timeline` names a document.

| Row | Content |
|---|---|
| Source | `satellite_imagery_timeline`, with lineage addressed to the document's SHA-256. |
| Entity | One spiderweb-owned `site_imagery_series` entity per site. Its id is derived from the producer entity id and **never equals it**: equivalence is the hub's call (hub ADR 0009). |
| Observation `satellite_scene` | One per admitted scene, observed at its acquisition time. |
| Observation `satellite_visible_change` | One per scored comparison. Same-epoch and unknown-epoch pairs make no claim and are not exported. |

Observations point at the series entity through `entity_id` and carry the registering
producer's id in `attributes.producer_entity_id`, the external site id, and the scene or
comparison context. Scene rows declare `CURATED`, change rows `COMPUTED`, and both a
representative point; no row declares an observation state, so absence is never asserted.
Row confidence is bounded by the site's ceiling. A scene observation's id includes the
scene id as well as the artifact id, so identical pixels in two scenes still yield two
observations. Rows carry `synthetic` from the document, and `--mode production` refuses synthetic rows. An invalid document fails the
export instead of being skipped. Hub schemas are frozen: no hub schema change is proposed.

## Operating rules

- No default writes. The command prints a summary and writes only with `--out`, and it
  does not replace an existing file without `--overwrite`.
- Provider credentials come from environment variables only. They are never committed,
  logged or echoed. The live stub reads none: it raises a typed error and fetches nothing.
- Tests run offline against `synthetic: true` fixtures. The manifest contract's fixture
  rule still applies: a `synthetic: false` record may not reference fixture, test or mock
  assets.
- Live acquisition, when wired, must pass each scene through the satellite source manifest
  and `readiness/satellite_ingest.py`. Offline, `tests/test_site_timeline_export.py`
  confirms that synthetic scenes produce manifests the ingest accepts.
- Nothing here is evidence of record. All output is provisional until the hub reviews it.

## Open items

1. Hub confirmation of the precedence position above.
2. Whether hub ADR 0006 applies to this repository's `imagery/` package.
3. Live Sentinel-2 acquisition: needs credentials supplied through environment variables,
   and an adapter that is replaced when the hub acquisition runtime ships.
4. The first real site list depends on aguayluz-pr merging its solid-waste registry work.
   Only synthetic sites exist today.
5. Every threshold, weight and window is uncalibrated. Calibration needs real imagery and
   a labelled set.
6. No contradiction source is wired, so the first test case stays open: the registry
   records the Arroyo landfill as closed in 2019, while an undated screenshot suggests
   activity. Only dated imagery can discriminate.
7. Aerial-archive licensing for pre-2015 baselines is unverified.
