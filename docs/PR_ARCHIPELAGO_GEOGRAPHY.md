# PR_ARCHIPELAGO_GEOGRAPHY

## Status

`PROVISIONAL / EMPIRICAL CLOSURE IN PROGRESS`

This capability replaces main-island-centric assumptions with a bounded,
auditable Puerto Rico archipelago substrate. It does **not** claim public-
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
`cayo`, `islet`, `islote`, `rock`, reef, ridge, shoal, or another term does not
by itself establish canonical type or identity.

## Geometry representation rules

Geometry representation is independent of canonical feature type and identity.
Permitted representations include source-native `POINT`, `LINE`, `POLYGON`,
`MULTIPOINT`, `MULTILINE`, `MULTIPOLYGON`, and explicitly labeled derived
representations.

A GNIS representative point is real source-native geometry but does not prove a
canonical footprint. Likewise, proximity to NOAA/CUSP shoreline or obstruction
evidence is corroboration/candidate evidence only. A polygonized shoreline is a
derived discovery geometry and cannot become a canonical land polygon without a
separate hard binding.

`polygon absence != geometry absence`.

## Denominators

Maintain at least four independently auditable sets:

1. `NAMED_CURRENT` — authoritative current named-feature manifestations.
2. `GEOMETRIC_CURRENT` — authoritative current geometry manifestations across
   appropriate representations; this must not be interpreted as a polygon-only
   denominator.
3. `HISTORICAL` — historical names/geometries/features; may include vanished or changed features.
4. `OPERATIONAL` — features exposed to Spiderweb runtime spatial classification.

Do not coerce equality among these sets. For each proposed equivalence compute
`INTERSECTION`, `A_ONLY`, `B_ONLY`, `UNION`, and `SYMMETRIC_DIFFERENCE` using
stable IDs or adjudicated canonical IDs, never names alone.

## Frozen current empirical source state — 2026-08-22

The following source manifestations are frozen and must be reused rather than
reacquired merely because another PR commit is made:

- GNIS current Puerto Rico source manifestations, including 148 current
  `Island`-class Feature IDs and the frozen FullModel/DomesticNames products.
- Census TIGER/Line 2025 state/coastline support manifestations.
- Puerto Rico SIGE manifestations already frozen by the current acquisition
  lanes; blocked WFS requests remain blocked manifestations and are never
  interpreted as source absence.
- NOAA NGS current Puerto Rico project denominator: 15 project codes, 15/15
  metadata manifestations frozen, and 15/15 exact NSDE project archives frozen.
- NOAA CUSP Puerto Rico bounded index: 40/40 index tiles decoded, exactly two
  download cells (`N15W065`, `N15W070`) discovered, and 2/2 exact packages
  frozen.

The exact NOAA project archive contract was recovered from the frozen NSDE
client code as `/downloads/<project-id>.zip`; CUSP uses
`feature.properties.name -> /downloads/<name>.zip`. Failed guessed URLs and the
stale NOAA response remain preserved as source-manifestation evidence rather
than being deleted after the exact contract was recovered.

## Current geometry audit state

Using derived polygon candidates from frozen Census, SIGE and NOAA shoreline
linework, 113 of the 148 GNIS current `Island` Feature IDs are representative-
point contained and 35 are not. The arithmetic closes as `148 = 113 + 35`.

Those 35 are **not** classified as geometry absence. Every GNIS manifestation
retains its source-native point representation. For the 35 polygon-
noncontainment cases, NOAA/CUSP line distances and NOAA point candidates are
recorded only as diagnostic/corroborating evidence. The current evidence ledger
shows 31/35 within 1 km of frozen NOAA/CUSP shoreline and four beyond 1 km.

The four >1 km cases were initially:

- GNIS 1609822 — Cayo Largo
- GNIS 1611372 — Las Lavanderas del Oeste
- GNIS 1613035 — Cayo Fanduca
- GNIS 2575426 — Las Lavanderas

Current NOAA Coast Pilot morphology hardens two without using proximity as an
identity join: Cayo Largo is described as a largely submerged/awash ridge, and
Cayo Fanduca as a few bare rocks. Those cases therefore do not justify a
mandatory single emergent-land polygon. The two Las Lavanderas cases remain
current morphology/footprint OPEN.

A same-name apparent contradiction was also resolved by stable ID rather than
name: `Piragua de Afuera` GNIS 1611676 is polygon-covered while GNIS 1613390 is
polygon-noncontained. They are distinct source identities and must not be
collapsed because their official names are equal.

## Current SIGE identity residue

Four SIGE insular rows retain complete nonempty candidate sets but remain
canonical `UNRESOLVED`:

- `Cayo de Ratones`
- `Cabeza de Perros`
- `Isla Maguelles`
- `Cayo de Caña Gorda`

Independent public-source corroboration has been recorded for all four, but no
row is promoted. In particular, the Caña Gorda evidence exposes an explicit
source-taxonomy conflict (`reef` vs GNIS `Island/Cayos`) and the Cabeza de Perros
area contains three separate current GNIS stable IDs. These contradictions and
cardinalities remain visible.

## Present-day source families

- USGS / U.S. Board on Geographic Names — GNIS naming authority and stable
  source Feature IDs.
- NOAA National Geodetic Survey — project shoreline/coastal mapping and NSDE
  CUSP manifestations with independent project/date lineage.
- U.S. Census Bureau — legal/administrative and coastline support geometry; not
  a canonical land-feature denominator.
- Puerto Rico government GIS / planning / natural-resources manifestations —
  independent local-authority evidence; blocked services are not negative
  evidence.
- NOAA/USACE elevation and topobathy products — corroboration/discovery where
  applicable, not naming authority.

Each acquired manifestation records or must record URL/service/layer/query,
retrieval UTC, refresh/update date when supplied, raw bytes, SHA256, schema,
row/feature count, CRS, geometry type, and any Z/M loss.

## Historical vector

Historical GNIS records/variants are one input, not the entire historical
universe. Historical USGS topographic maps, NOAA nautical charts, and Puerto
Rico historical map/chart sources are collected independently. Preserve
`CURRENT`, `HISTORICAL_ONLY`, `RENAMED`, `MERGED`, `SPLIT`, `DISAPPEARED`, and
`UNRESOLVED` as temporal conclusions only when evidence supports them.

Current B-state includes eight bounded NOAA historical Puerto Rico shoreline
records and 8/8 exact NSDE historical project archives with arithmetic closed.
These remain B-only and cannot fill A residue without a separate temporal and
identity adjudication.

Historical exhaustion is not a prerequisite for bounded present-day
certification if the current denominator fully closes, but B itself remains
independently OPEN until its public-source universe is exhausted.

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

For any partition of the current geometry audit, all retained, excluded,
candidate-only and unresolved states must also sum exactly to the controlling
source denominator.

For the current canonical denominator, all retained/excluded/duplicate states
must close with no unexplained remainder. Current certification requires zero
unresolved current identity residue, zero unresolved duplicate residue, zero
unexplained canonical geometry residue, frozen source snapshots, explicit
scope, and passing schema/geometry/count gates.

## Certification boundary

`CURRENT_PR_ARCHIPELAGO = PASS` is permitted only for the explicitly frozen
current source universe after denominator closure. It must never be reported as
universal historical or public-source exhaustion unless those larger scopes
are independently proven.

Current state:

`CURRENT_PR_ARCHIPELAGO = OPEN`

`GEOMETRIC_CURRENT = OPEN`

`SIGE_CANONICAL_IDENTITY = OPEN`

`HISTORICAL_ARCHIPELAGO_EXHAUSTION = OPEN`

## Integration

The capability lives under `spiderweb.spatial` and is additive. Existing passed
Spiderweb bridge/export behavior is reused rather than rebuilt. The current
`readiness/spiderweb_intake.py` centroid heuristics remain legacy behavior until
a later integration change explicitly replaces only the geographic assumptions
with a certified archipelago provider and regression tests.

C remains certification-gated. Provider admission must fail closed on OPEN
snapshots, nonzero residue, arithmetic failure, missing artifacts or hash
mismatch. Runtime activation remains blocked while
`CURRENT_PR_ARCHIPELAGO != PASS`.
