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
| 1 | Config / registry (`pin_registry.yaml` + loader alias) | **done** |
| 2 | RLSM validation schemas | **deferred — see below** |
| 3 | Code (`pipeline/`, `integration/`, `server/`, `scripts/`, …) | pending |
| 4 | Tests + non-legacy docs | pending |

**Stage 2 deferred (cross-repo coupling).** The `poi`-named schemas — `labeled_pois`,
`unlabeled_poi_candidates`, `ocr_normalized_labels`, `manual_review` — are dormant,
validation-only contracts in this repo. The RLSM pipeline that produced their artifacts
(`outputs/*_pois.csv` with `poi_id` / `poi_type_guess` columns) **migrated to
[skywatcher-pr](https://github.com/jotaele44/skywatcher-pr)** (PRs #110/#111), so those
artifacts are no longer generated here and no in-repo code validates against these schema
names. Renaming only our schema identity (`$id` / filename) would desync the name from the
`poi_*` columns it still describes; renaming the columns/artifacts would make our schemas
reject the CSVs skywatcher-pr still emits. This schema family therefore **awaits
coordination with skywatcher-pr** and is intentionally left untouched until then.
