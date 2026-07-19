# PR Natural-Features Gazetteer — Federation Contract

`spiderweb-pr` is the **owner/curator** of the canonical Puerto Rico
natural-features gazetteer. Every other PRII producer consumes a **domain slice**
of this one dataset rather than maintaining its own copy — a single source of
truth is what keeps place names from drifting across repos.

## Source & derivation

Derived from the authoritative **USGS GNIS** `DomesticNames` table for Puerto
Rico (public domain). The compact source extract is committed at
`registry/natural_features/source/gnis_pr_domestic_names.json` so the build is
reproducible without the 7.8 MB GeoPackage. Populated/administrative classes
(`Populated Place`, `Civil`, `Military`, `Census`, `Area`) are excluded; one
off-island centroid error (`Caribbean Sea`) is dropped by the PR bounds filter.

`feature_type` is derived from the GNIS `feature_class` **plus the Spanish name
prefix**, because GNIS files rivers and quebradas both as `Stream` and many
quebradas as `Valley` (`Río…`→river, `Quebrada…`→quebrada, `Pico…`→peak).

Rebuild: `python3 scripts/build_natural_features.py` (add `--gpkg PATH` to refresh
the source extract from a raw GNIS GeoPackage). Slice:
`python3 scripts/build_slices.py`.

## Record shape

The contract schema is `schemas/pr_natural_feature.schema.json`. Every record
carries a stable `gnis_id`, a readable unique `canonical_id`
(`^place_<type>_<ascii_snake>$`), the accented `canonical_name`, the accent-folded
`normalized_name` (the federation name join key), `feature_type`, `group`,
`municipality` (PR municipio), and `lat`/`lon` (WGS84, inside PR bounds).

## `feature_type → group`

| group | feature_types | count |
|---|---|---|
| hydro | river, quebrada, stream, channel, canal, lake, reservoir, spring, waterfall, basin, gut, wetland | 991 |
| terrain | mountain, peak, ridge, mountain_range, valley, cliff, gap, flat, plain, woods | 375 |
| coastal | cape, bay, beach, bar, island | 616 |

## Consumer slice-map

| Repo | Slice | File |
|---|---|---|
| spiderweb-pr | full (1,982) | `registry/natural_features/pr_natural_features.{json,geojson}` |
| aguayluz-pr | hydro (991) | `slices/aguayluz_pr_natural_features.{json,geojson}` |
| skywatcher-pr / ovnis-pr | terrain + coastal (991) | `slices/skywatcher_ovnis_pr_natural_features.{json,geojson}` |
| centinelas-pr | all, name-only resolver (no geometry) | `slices/centinelas_pr_natural_features_resolver.json` |
| moneysweep-pr | none (municipality context via its own crosswalk) | — |
| thehub-pr | schema + rules (+ optional derived index); correlates on emitted keys | — |

## Change protocol

Changes to `schemas/pr_natural_feature.schema.json` or the `feature_type`/`group`
enums are a **lockstep cross-repo event**: bump the version, regenerate the master
and all slices, and open coordinated PRs in every consuming repo (same discipline
as moneysweep's `moneysweep_*` exported schemas). Consumers pin the master's
`_source_sha256` recorded in each slice header.

## Deferred (needs hub coordination)

- Registering a `natural_feature` value in the closed `entity_type` enum of
  `schemas/federation_entity.schema.json` (+ the discriminator maps in
  `scripts/federation_export.py`) so features export as first-class federation
  entities. Deferred here because that enum is pinned by the hub's
  contract-compat golden files and must change in lockstep with `thehub-pr`.
- Protected natural resources (reservas naturales / bosques estatales): GNIS has
  no protected-area class for PR; a DRNA/USFWS source is a follow-up.
