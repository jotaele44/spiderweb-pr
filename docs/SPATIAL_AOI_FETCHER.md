# Spiderweb AOI-Driven Spatial Fetcher v0.1

## Purpose

Resolve a task AOI against an authoritative source-tile catalog, reuse any locally certified bytes, fetch only missing source tiles when an authoritative URL binding exists, and keep the canonical Spiderweb `Cell_ID` grid as a downstream federation coverage ledger.

## Critical grid constraint

The current canonical grid (`registry/spatial/pr_grid_full_cell_index_saturated.csv`) is a stable 256x384 federation join grid, but its stored geometry is pixel-space (`Pixel_X_*`, `Pixel_Y_*`, `Centroid_X`, `Centroid_Y`). There is no certified CRS/geographic transform in the current grid schema. Therefore v0.1 **must not** derive AOI-to-Cell_ID bindings from those pixel coordinates.

The spatial order is:

```text
Task AOI
  -> authoritative source-tile catalog
  -> required source tiles
  -> local cache validation
  -> fetch only missing tiles when source URLs are resolved
  -> task-local VRT/mosaic
  -> derived terrain products
  -> Cell_ID binding only after a certified grid georeference exists
```

This preserves the federation rule that overlays may be many-to-many without inventing geographic meaning for the pixel grid.

## Existing DEM integration

This module extends the repository's existing DEM stack rather than replacing it:

- `tools/pr_dem_batch_runner.py` already selects local GeoTIFFs by WGS84 bounding-box intersection.
- `tools/pr_dem_one_tile_pilot.py` already performs rasterio-based reprojection and terrain screening.
- `pyproject.toml` already exposes the `dem` extra with rasterio.

`tools/spatial_aoi_fetcher.py` adds the missing acquisition layer before those processors.

## First provider: PRVI_1m_DEM_2018

The first provider contract is registered in `configs/spatial_dataset_providers.json`.

The supplied VRT used during design has these observed properties:

- CRS: NAD83 / UTM zone 20N (`EPSG:26920`)
- pixel size: 1 m
- raster size: 140012 x 70012
- source references: 109 GeoTIFF `ComplexSource` entries
- source tile dimensions reported by the VRT: 10012 x 10012 pixels

The VRT contains **relative local source filenames**, not authoritative download URLs. The repository therefore leaves both `catalog_path` and `source_url_template` unbound by default. Operators pass the VRT with `--catalog`; network acquisition remains fail-closed until a verified provider URL/index binding is added.

## Discovery-first planning

Example:

```bash
python tools/spatial_aoi_fetcher.py \
  --dataset PRVI_1m_DEM_2018 \
  --catalog /path/to/PRVI_1m_DEM_2018.vrt \
  --bbox WEST,SOUTH,EAST,NORTH \
  --aoi-crs EPSG:4326 \
  --output-dir outputs/spatial_aoi_fetch/boqueron
```

The command writes `acquisition_plan.json` before any network transfer. The plan records:

- requested AOI and CRS;
- transformed AOI in provider-native CRS;
- required source-tile set;
- local cache state per tile;
- cached-valid and missing counts;
- unresolved-source-URL count;
- known expected byte total when the provider supplies sizes;
- current cell-binding status.

## Cache semantics

Default cache root:

```text
data/cache/spatial/<dataset_id>/
```

Per-tile states include:

- `ABSENT`
- `INVALID_EMPTY`
- `INVALID_SIZE`
- `INVALID_HASH`
- `INVALID_RASTER`
- `LOCAL_VALID_UNPINNED`
- `LOCAL_HASH_VALID`

A second overlapping AOI reuses any valid cached tile and performs zero redundant download for that tile.

## Fetch semantics

`--fetch` activates acquisition only when the selected tile has a resolved source URL.

Downloads use a `.part` file and HTTP Range when a partial transfer exists. Source bytes are retained in the cache; downstream clipping should occur only after source-byte preservation.

Default behavior is fail-closed. If any required tile cannot be acquired/validated, the receipt reports:

```text
BLOCKED_INCOMPLETE_SOURCE_BYTES
```

`--allow-partial` may be used for explicitly partial workflows, but the resulting data must not be treated as complete AOI coverage.

## Task-local VRT

`build_task_vrt()` invokes `gdalbuildvrt` when available. It never rewrites the source tiles. If GDAL's VRT builder is unavailable, the operation reports a blocked status rather than silently creating a different product.

## Cell-grid binding contract

The intended many-to-many relation is:

```text
Cell_ID <-> dataset_id/source tile
```

with fields such as intersection area, cell coverage percentage, source version, source SHA-256, byte state, and analytical state. That binding is intentionally deferred until the canonical pixel grid receives a certified geographic transform or authoritative geographic cell geometry.

Spatial coverage, byte availability, and analytical coverage must remain separate states.

## Boqueron test status

The current Boqueron task cannot yet satisfy the v0.1 end-to-end fetch gate for two independent reasons:

1. the provider VRT has no authoritative network URL binding; and
2. the canonical Cell_ID grid is not georeferenced.

The resolver can still determine whether an AOI intersects the supplied VRT footprint and enumerate source tiles when the VRT is passed locally. A complete Boqueron acquisition test must not be claimed until an authoritative PRVI source URL/index is bound and the AOI is confirmed to fall within that catalog's spatial coverage.

## Non-promotion rule

Terrain or imagery proximity is an association only. This fetcher does not classify DEM features as caves, tunnels, bunkers, utilities, or other subsurface infrastructure.
