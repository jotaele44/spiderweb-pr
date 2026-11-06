# Site Imagery Timeline Contract

Status: **Proposed. Not implemented.** No code in this repository produces these records yet.
Date: 2026-11-05

## Purpose

Define how spiderweb-pr would build a dated satellite-scene timeline for sites that another
producer registers (first case: Puerto Rico solid-waste sites, a registry proposed for
aguayluz-pr in its ADR-0004), and how that timeline reaches the hub for visual review.

spiderweb-pr owns the imagery observations. It does **not** own the site registry, site
identity, or any claim about why a site changed.

## Status and precedence

**Interim path.** Hub ADR 0006 (Accepted, 2026-07-29) moves satellite-provider network
access, credentials and the imagery cache into thehub-pr. That ADR names thehub-pr and
skywatcher-pr, not this repository, and the hub has contracts for it but no acquisition
runtime yet. Until that runtime ships, acquisition here is repo-internal. Every adapter
that touches a provider lives behind one seam, so replacing it with hub-brokered artifacts
later changes one module. Trigger to revisit: the hub acquisition runtime ships.

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

## Inputs

A frozen site list, supplied as data. No code is imported from another repository.

| Field | Meaning |
|---|---|
| `external_site_id` | Opaque id minted by the registering producer. Never parsed or interpreted here. |
| `entity_id` | The registering producer's hub entity id (`ent_` plus 32 hex), when known. Used only to link observations. |
| `geometry` | WGS84 point or polygon. |
| `geometry_precision` | Stated coordinate precision. Coarse seeds (2-3 decimals, roughly 100 m to 1 km) get a wide chip and low geometric confidence. |

Proximity, name similarity and coordinates never establish that two records are the same
site. Equivalence is adjudicated by the hub. A pin in `configs/pin_registry.yaml` is a
discovery seed, not a site record.

## Admission to a timeline series

- Only scenes with a provider-stated acquisition time (`acquired_at`, required by
  `docs/contracts/SATELLITE_SOURCE_MANIFEST.md`) enter a series.
- Undated captures, such as a consumer-map screenshot, are class `UNDATED_BASEMAP_CAPTURE`:
  epoch unknown, excluded from series and from any change claim.
- A scene whose cloud cover exceeds the cutoff is excluded. The cutoff is a tunable
  heuristic, configurable, starting at 20 percent. It is not a measured threshold.

## Epoch classes

| Class | Definition | Disposition |
|---|---|---|
| `same_epoch` | Same provider imagery date and tile generation | Render consistency only |
| `near_epoch` | Different render or date, insufficient separation | Review |
| `cross_epoch` | Meaningfully different date, provider or capture cycle, after same-ground binding | Valid comparison |
| `unknown_epoch` | Date or provider unavailable | Review; never promoted |

These follow skywatcher-pr's SATIM mixed-epoch validation spec. They are re-implemented
from the spec here, not imported, because this repository forbids cross-repo imports. The
existing score-delta tool in `earthgpt/temporal_epoch_compare.py` is not extended: it
compares scores between pipeline snapshots and carries no epoch provenance.

## Change claims

Allowed: **visible change between two dated epochs**, nothing more.

- At Sentinel-2 resolution (10 m) only coarse classes are allowed: `EXPANSION`,
  `CONTRACTION`, `SURFACE_COVER_CHANGE`. No per-feature claims below the resolution.
- Temporal classes: `STABLE`, `PROBABLE_CHANGE`, `CONFIRMED_VISIBLE_CHANGE`,
  `ARTIFACT_DRIVEN_CHANGE`, `INSUFFICIENT_EPOCH_ALIGNMENT`.
- The pixel-difference signal in the `imagery/` package is a first-pass, uncalibrated
  measurement and must be labelled as such.

Forbidden: any causal inference (why a site changed), any statement about legality,
operator conduct or intent, any identity claim from proximity, and any change claim that
spans an unknown or artifact-driven epoch. Before and after provenance stay separate, and
an original epoch record is never rewritten.

## Outputs

Three separate objects. They may reference one another and are never collapsed into one
mutable manifest (hub ADR 0006, object separation).

1. **Acquisition record**, carrying the facts of the hub's `acquisition_receipt.v1`
   contract: provider, requested and completed times, outcome, a SHA-256 request digest,
   and artifact ids.
2. **Source artifact**: the scene content, addressed by its SHA-256, held in the
   git-ignored cache. Pixels are not committed. Provider licensing varies.
3. **Provisional change observation**, shaped like the hub's `satim_provisional_signal.v1`
   contract: method, method version, parameters, result, confidence, `provisional: true`,
   and review status.

The hub receives **`observations` rows** (the hub's `federation_observation` schema),
following hub ADR 0008, where this repository already publishes geometry as observation
rows naming another producer's entity. Rows carry `observation_type`, `observed_at` (the
scene acquisition time), an optional `entity_id`, a point `location`, a `synthetic` flag
and free-form `attributes` that include the epoch class, cloud cover and manifest digest.
Row `confidence` is bounded by the chip's geometric confidence. Every row is marked
provisional until the hub certifies it. Hub schemas are frozen: no hub schema change is
proposed.

## Operating rules

- No default writes on fetch. Persistence happens only on explicit request.
- Provider credentials come from environment variables only. They are never committed,
  logged or echoed.
- Tests run offline against `synthetic: true` fixtures. The manifest contract's fixture
  rule still applies: a `synthetic: false` record may not reference fixture, test or mock
  assets.
- The satellite source manifest remains the ingest gate for every scene.
- Nothing here is labelled certified evidence.

## Open items

1. Hub confirmation of the precedence position above.
2. Whether hub ADR 0006 applies to this repository's `imagery/` package.
3. The first site list depends on aguayluz-pr freezing its solid-waste denominator, which
   has not happened.
4. Aerial-archive licensing for pre-2015 baselines is unverified.
