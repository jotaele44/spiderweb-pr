# D02 — Internal geographic dataset register

What this repository already holds or registers, counted from the files on
2026-11-26. Counts are `COMPUTED` by loading each file; nothing was taken from
a document's own claim about itself.

## Source and provider registries

Seven registries exist. Each belongs to one lane. None references another.

| Registry | Entries | Lane |
|---|---|---|
| `configs/location_query_providers.json` | 16 providers | Location query |
| `configs/location_query_source_bindings.json` | 7 bindings | Location query |
| `configs/pr_archipelago_sources.json` | 8 sources | Archipelago geography |
| `configs/remote_monitoring/providers.yaml` | 8 providers | Remote monitoring |
| `configs/spatial_dataset_providers.json` | 1 provider | Elevation by area of interest |
| `manifests/pr_hydrography/source_registry.csv` | 4 sources | Hydrography |
| `spiderweb/subsurface/sources.py` | 33 source specifications | Subsurface |

## Dataset and asset inventories

| Inventory | Entries | Notes |
|---|---|---|
| `data_sources/elevation/dem_platform_catalog.yml` | 30 products, 19 non-product registrations, 6 recorded conflicts | The only cross-lane dataset catalogue; elevation only. Holds both pilot surveys with their windows. |
| `data_sources/elevation/lidar_comparison_tiles.json` | 8 sites | Files used by the lidar comparison of 2026-11-24; records 477 files of this family over Puerto Rico |
| `evidence/dem_sources/lidar_comparison_2026-11-24/tiles_provenance.json` | 18 files with SHA-256 | Bytes not kept. Three are pilot files. |
| `registry/spatial/source_manifestations.json` | 28 files | USGS 3DEP 1 m, one bounding box. Before this work 20 of 28 had no footprint; no checksum on any |
| `registry/geo_sar/pilot_001_asset_ledger.json` | 28 files | Same 28, all footprints read from the files, bound to 42 segments |
| `data/tiger/2026/pr_source_inventory.csv` | 796 rows | Census TIGER 2026 file inventory |
| `registry/spatial/cell_source_binding.json` | 0 bindings | Withheld: refers to the provisional first grid, not Grid V2 |
| `registry/natural_features/` | not counted here | Natural feature gazetteer and per-consumer slices |
| `registry/access_points/` | not counted here | Inland and off-shore registries with their own source lists |

## Not in the repository

| Item | State | Why |
|---|---|---|
| Spiderweb Master geographic baseline | UNVERIFIED | Referenced as a local GeoPackage by `scripts/populate_dataset_layers.py`; the file is not tracked and was not available |
| Municipality, barrio, tract and place geometry | UNVERIFIED | Built by `server/ingestion/ingest_tiger_pr.py` into ignored paths; only manifests and hashes are tracked |
| Watershed boundaries | ABSENT | No data and no code |
| Imagery | ABSENT | Imagery is served from a public provider bucket at run time; none is stored |
| Grid V2 cell tables | Not tracked | Deterministic from `spiderweb/geographic_grid_v2.py`; the manifest is tracked |
| Geographic datasets of the other Federation repositories | BLOCKED | Skywatcher-PR, AguaYLuz-PR, MoneySweep-PR, Centinelas-PR and OVNIS-PR were not attached to the session |

## Denominator

The internal dataset denominator **cannot be closed from this environment**.
What is closed is narrower and exact:

- 28 of 28 catalogue-listed 1 m elevation files for the pilot bounding box are
  registered with file-derived footprints (catalogue reported 28, returned 28).
- 0 of 28 are held. 3 of 28 have a SHA-256 from an earlier run.
- The family has 477 files over Puerto Rico by the elevation lane's count of
  2026-11-24; 28 are registered with footprints. That count was not re-derived
  here.

Everything else in the tables above is an inventory of registrations, not a
verified count of datasets. It stays `UNVERIFIED` until the external items are
supplied and the seven registries are indexed against one another.

## Duplicate and superseded registrations

- Dataset identity for the two surveys is spelled differently in the older
  asset registry and in the elevation catalogue. The pilot ledger carries
  both side by side (`dataset_id`, `dataset_catalog_id`). Choosing one is
  queued in D18.
- The 28 files are now described in two places. The older file is left as it
  was; the pilot ledger records, per file, whether it agrees
  (`prior_registration.differences` is empty for all 28).
- `registry/spatial/cell_source_binding.json` and
  `configs/spatial_dataset_providers.json` still describe themselves as blocked
  on the first grid's georeference. Grid V2 removes that reason. They were not
  changed; re-pointing them is queued in D18.
- The older registry classes each zone 20N file as an alternate of a zone 19N
  file. Measured footprints do not support that file to file; see D17 and
  pilot gap 006.
