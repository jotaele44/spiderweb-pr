# Spiderweb Pin Model (v1)

The Pin model is the canonical vocabulary for every spatially-referenced object in
Spiderweb-PR. It replaces the legacy **POI / Entity / Feature / Location** language.

> **A Pin** is any mapped object, place, asset, event location, signal, anomaly,
> candidate, infrastructure node, or analytic marker that can be spatially referenced
> and assigned evidence metadata.

## Canonical hierarchy

Visibility class stays the **top** folder (project decision); the Pin model nests beneath:

```
SPIDERWEB_PR
└── Visibility Class   (V3 / V2 / V1 — access gate)
    └── Domain         (Hydrology, Utilities, Institutional & Civic, …)
        └── Pin Group  (major folder inside a domain)
            └── Pin Class   (specific category — e.g. Power Substation)
                └── Pin Layer   (one geometry type / schema variant)
                    └── Pin     (atomic mapped object)
```

| Term | Definition |
|------|------------|
| Domain | Highest thematic container |
| Pin Group | Major folder inside a domain |
| Pin Class | Specific category of mapped object |
| Pin Layer | Actual GIS/table layer holding one geometry type or schema variant |
| Pin | Atomic mapped object (location, geometry, source, confidence, classification) |
| Pin Link | Relationship between pins (`school operated_by agency`) |
| Master Pin Registry | Islandwide canonical index of every pin |

## Artifacts

| File | Role | Source |
|------|------|--------|
| `configs/pin_model.yaml` | Hand-authored model definition + language rules | — |
| `schemas/pin.schema.json` | Master Pin Registry record schema | — |
| `schemas/pin_link.schema.json` | Pin Link schema | — |
| `configs/pin_taxonomy.yaml` | Nested folder tree in Pin terms | **generated** |
| `configs/master_pin_registry.yaml` | Flat islandwide index, one row per Pin Layer | **generated** |

Regenerate the two generated artifacts from `configs/layer_catalog.yaml`:

```
python3 scripts/build_pin_registry.py            # write
python3 scripts/build_pin_registry.py --dry-run  # audit only
```

This pass is **labels-only**: zero atomic pins are bound (`pins: []`), every Pin Layer is
`status: planned`. Coordinates/geometry land in a later pins-pass.

## Lifecycle flags

Each Pin Layer carries one flag; the builder **fails on any ORPHAN** (zero-orphan contract):

- **WIRED** — pipeline emits this Pin Layer.
- **GHOST** — catalogued and expected, not yet emitted.
- **PLANNED** — reserved name, no producer yet.
- **DEPRECATED** — superseded; retained for lineage.
- **ORPHAN** — served/emitted but absent from the taxonomy → **fatal**.

## Rename policy (Core Semantic Replacement)

| Avoid | Use |
|-------|-----|
| POI, Entity | Pin |
| Feature | Pin / Pin Geometry |
| Dataset folder | Pin Group |
| Subfolder | Pin Class |
| GIS layer | Pin Layer |
| Master entity table | Master Pin Registry |
| Relationship, Graph edge | Pin Link |
| Candidate / Confirmed location | Candidate / Confirmed Pin |

**Carve-out — tokens that are NOT renamed.** These are externally-mandated wire/format
constants, not domain vocabulary; renaming them breaks interchange formats and tooling:

- GeoJSON `"type": "Feature"` / `"type": "FeatureCollection"` (RFC 7946)
- GeoPackage `gpkg_*` tables and the `features` data type
- OGC / GDAL `feature` API surface
- Source-dataset SQLite/field names preserved per `location_naming_guardrails`

The rename of the existing pipeline/backend/frontend domain vocabulary is staged as a
tracked follow-up migration on top of this canonical Pin layer.

## Staged migration status

| Stage | Area | Status |
|-------|------|--------|
| 1 | Config / registry (`pin_registry.yaml` + loader alias) | **done** (PR #126) |
| 2 | RLSM validation schemas (`labeled_pins`, `unlabeled_pin_candidates`) | **done** (PR #139) |
| 3a | Internal code identifiers (`poi_features`, `_build_poi_candidates`, `domain=`) | **done** (PR #136) |
| 3b | Artifact filenames (`*_poi_candidates.geojson`, `.qml`) + tests + docs | **done** (PR #137) |

**Stage 2 complete (coordinated with skywatcher-pr).** The formerly `poi`-named schemas
have been fully renamed: `labeled_pois` → `labeled_pins`, `unlabeled_poi_candidates` →
`unlabeled_pin_candidates`; column names `poi_id` → `pin_id` and `poi_type_guess` →
`pin_type_guess` updated in all schemas; artifact paths updated to `outputs/labeled_pins.csv`,
`outputs/unlabeled_pin_candidates.csv`, and `outputs/manual_review_labeled_pins.csv`;
`labeled_poi_low_conf` enum value in `manual_review.schema.json` updated to
`labeled_pin_low_conf`. skywatcher-pr now emits the renamed output files and columns.
Internal skywatcher SQLite table/column names (`labeled_pois`, `poi_id` in SQL) are a
separate deferred migration outside this stage's scope.

## Preserved carve-outs (intentionally NOT renamed)

The tokens below appear in the codebase with `poi` in their name but are **wire/data
constants**, not internal identifiers. Renaming them would break serialized artifacts,
cross-module data contracts, or external interchange formats.

| Token | Location | Reason preserved |
|-------|----------|-----------------|
| `"poi_a"`, `"poi_b"` | `integration/ilap_airspace_bridge.py` (emitted); `readiness/spiderweb_intake.py` (consumed) | GeoJSON feature-property keys written to disk and read back by the intake parser; changing them would invalidate existing exports |
| `candidate_type: "poi"` | `readiness/spiderweb_intake.py` (:222, :495, :665) | Routing sentinel value stored in exports; changing it silently drops or misroutes previously-produced candidate records |
| `ROLE = {"poi": "node", …}` | `readiness/spiderweb_intake.py` (:376) | Dict key matched against `candidate_type`; must stay in sync with the above |
| `poi_aoi_corridor_candidate` | `readiness/spiderweb_spatial_lane.py` (domain routing key) | Free-form domain tag value propagated from the moneysweep-pr router derivative; renaming would desync with the upstream producer |
| `poi_group` | `scripts/populate_dataset_layers.py` | GeoJSON property key written to the dataset-layers export; consumed by downstream tooling |
| `POI_CANDIDATE` | `configs/location_naming_guardrails.yaml` | Enum value in a config schema; a semantic rename here requires coordinated update to any tool that reads the guardrails |
| `poi_*` config-loader alias keys | `pipeline/config_loader.py` | Backward-compat aliases so old configs referencing `poi_registry` still load; intentional bridge to Stage 2 |
| `poi_name`, source-field reads | various harvesters | Column names from external source data; cannot be renamed unilaterally |
| `labeled_poi_low_conf` in `manual_review` item_kind enum | `schemas/manual_review.schema.json` | Renamed to `labeled_pin_low_conf` in Stage 2 |
