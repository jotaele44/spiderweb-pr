# PR_ARCHIPELAGO_GEOGRAPHY

## Status

`PROVISIONAL / IMPLEMENTATION SCAFFOLD`

This capability replaces main-island-centric assumptions with a bounded,
auditable Puerto Rico archipelago substrate.  It does **not** claim public-
source or historical exhaustion merely because one geometry source is loaded.

## Controlling vector

A controls the present-day geographic denominator. B independently supplies
historical manifestations. C supplies archipelagic spatial semantics. Current,
historical, named, geometric, and operational denominators are intentionally
separate.

## Identity rules

Never prove canonical identity from `NAME_ONLY`, `NORMALIZED_NAME_ONLY`,
`COUNT_EQUALITY`, `NEAREST_ONLY`, `PROXIMITY_ONLY`, `SAME_CATEGORY`, or
`SOURCE_ABSENCE`.

Allowed cardinalities are `1:1`, `1:N`, `N:1`, `N:N`, `0:1`, and
`UNRESOLVED`. Tied top evidence remains `UNRESOLVED/REVIEW`.

Source taxonomy is preserved raw. A source calling a feature `island`, `cay`,
`cayo`, `islet`, `islote`, `rock`, or another term does not by itself establish
canonical type or identity.

## Denominators

Maintain at least four independently auditable sets:

1. `NAMED_CURRENT` — authoritative current named-feature manifestations.
2. `GEOMETRIC_CURRENT` — authoritative current land/emergent-feature geometry manifestations.
3. `HISTORICAL` — historical names/geometries/features; may include vanished or changed features.
4. `OPERATIONAL` — features exposed to Spiderweb runtime spatial classification.

Do not coerce equality among these sets. For each proposed equivalence compute
`INTERSECTION`, `A_ONLY`, `B_ONLY`, `UNION`, and `SYMMETRIC_DIFFERENCE` using
stable IDs or adjudicated canonical IDs, never names alone.

## Present-day source families identified for acquisition

These are source families, not yet frozen snapshots:

- USGS / U.S. Board on Geographic Names — GNIS Puerto Rico data. GNIS is the
  Federal naming standard and provides stable Feature IDs, official names,
  variants, coordinates, feature classes, and historical status.
- NOAA National Geodetic Survey — Puerto Rico shoreline/coastal mapping
  datasets. Use as high-resolution shoreline geometry manifestations with
  explicit project/date lineage; do not assume a single project covers every
  Puerto Rico island.
- U.S. Census Bureau — current TIGER/Line legal/administrative boundary and
  related geography products for independent administrative/geometry support.
- Puerto Rico government GIS / planning / natural-resources manifestations —
  use as independent local-authority candidates where a stable, downloadable
  dataset and metadata can be frozen.
- NOAA/USACE elevation and topobathy products — discovery/corroboration for
  small emergent features and geometry disagreement, not naming authority.

Each acquired manifestation must record URL/service/layer/query, retrieval UTC,
refresh/update date when supplied, raw bytes, SHA256, schema, row/feature count,
CRS, geometry type, and any Z/M loss.

## Historical vector

Historical GNIS records/variants are one input, not the entire historical
universe. Historical USGS topographic maps, NOAA nautical charts, and Puerto
Rico historical map/chart sources should be collected independently. Preserve
`CURRENT`, `HISTORICAL_ONLY`, `RENAMED`, `MERGED`, `SPLIT`, `DISAPPEARED`, and
`UNRESOLVED` as temporal conclusions only when evidence supports them.

Historical exhaustion is not a prerequisite for bounded present-day
certification if the current denominator fully closes.

## Spatial semantics

Runtime classifications must distinguish:

- land containment;
- coastal proximity;
- archipelagic position;
- municipal jurisdiction;
- territorial-water position;
- any later EEZ classification.

Operational archipelagic positions include `ON_MAIN_ISLAND`,
`ON_OUTLYING_ISLAND`, `ON_CAY`, `ON_ISLET`, `ON_OTHER_EMERGENT_FEATURE`,
`BETWEEN_INSULAR_FEATURES`, `NEAR_INSULAR_FEATURE`,
`OFFSHORE_WITHIN_ARCHIPELAGIC_ENVELOPE`,
`OFFSHORE_OUTSIDE_ARCHIPELAGIC_ENVELOPE`, and `UNRESOLVED`.

Never infer `ON_*` from proximity.

## Required arithmetic gates

For every source manifestation family:

`SOURCE_MANIFESTATIONS = IDENTITY_RESOLVED + IDENTITY_UNRESOLVED`

For the current canonical denominator, all retained/excluded/duplicate states
must close with no unexplained remainder. Current certification requires zero
unresolved current identity residue, zero unresolved duplicate residue, frozen
source snapshots, explicit scope, and passing schema/geometry/count gates.

## Certification boundary

`CURRENT_PR_ARCHIPELAGO = PASS` is permitted only for the explicitly frozen
current source universe after denominator closure. It must never be reported as
universal historical or public-source exhaustion unless those larger scopes
are independently proven.

Until authoritative datasets are acquired, frozen, reconciled, and tested:

`CURRENT_PR_ARCHIPELAGO = OPEN`

`HISTORICAL_ARCHIPELAGO_EXHAUSTION = OPEN`

## Integration

The capability lives under `spiderweb.spatial` and is additive. Existing passed
Spiderweb bridge/export behavior should be reused rather than rebuilt. The
current `readiness/spiderweb_intake.py` centroid heuristics remain legacy
behavior until a later integration change explicitly replaces only the
geographic assumptions with certified archipelago queries and regression tests.
