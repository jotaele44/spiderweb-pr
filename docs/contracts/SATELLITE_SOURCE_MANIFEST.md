# Satellite Source Manifest Contract

## Purpose

The Satellite Source Manifest defines the minimum source package contract for Puerto Rico-focused satellite and remote-sensing inputs consumed by PRII federation workflows.

This contract is fail-closed. A package that omits required source, asset, geometry, quality, or lineage fields must be rejected before runtime ingestion or downstream readiness scoring.

## Scope

This contract covers source metadata and provenance only. It does not define a downloader, STAC client, raster processor, adapter, UI, or producer repository implementation.

## Non-goals

- No live satellite download behavior.
- No external API credential handling.
- No STAC catalog client implementation.
- No raster tiling or image processing pipeline.
- No `run_all.py` wiring.
- No producer repository alignment.
- No Stage 3 runtime ingestion.

## Required package identity

Each manifest must include:

| Field | Requirement |
|---|---|
| `manifest_id` | Stable unique identifier for this source manifest. |
| `schema_version` | Contract version, starting at `1.0`. |
| `producer` | System or process that generated the manifest. |
| `created_at` | Manifest creation timestamp in ISO-like string form. |
| `synthetic` | Boolean indicating fixture/test/synthetic status. |

## Required source metadata

Each manifest must identify the remote-sensing source:

| Field | Requirement |
|---|---|
| `source.provider` | Provider, for example `esa`, `copernicus`, `usgs`, `nasa`, or `noaa`. |
| `source.collection` | Collection or product family, for example `sentinel-2-l2a`. |
| `source.platform` | Platform or satellite, for example `Sentinel-2A`. |
| `source.instrument` | Instrument, for example `MSI`, `SAR`, `OLI`, or `VIIRS`. |

## Required acquisition metadata

Each manifest must include:

| Field | Requirement |
|---|---|
| `acquisition.acquired_at` | Source acquisition timestamp. |
| `acquisition.processed_at` | Processing or product publication timestamp. |
| `acquisition.license` | License or access-use statement. |

## Required asset metadata

Each manifest must identify at least one asset reference:

| Field | Requirement |
|---|---|
| `asset.source_uri` | External URI, if the asset is externally referenced. |
| `asset.local_path` | Local path, if the asset is packaged locally. |
| `asset.checksum_sha256` | SHA-256 checksum for the referenced asset. |
| `asset.media_type` | Asset media type, for example `image/tiff` or `application/geo+json`. |

At least one of `asset.source_uri` or `asset.local_path` is required.

## Required geometry metadata

Geometry is locked to EPSG:4326.

| Field | Requirement |
|---|---|
| `geometry.crs` | Must be `EPSG:4326`. |
| `geometry.footprint` | GeoJSON Polygon footprint. |
| `geometry.bbox` | `[west, south, east, north]` bounding box. |

The default Puerto Rico validation envelope is:

```text
west  = -68.2
south = 17.8
east  = -65.1
north = 18.7
```

A source package outside this envelope must be rejected for Puerto Rico federation workflows unless a future contract explicitly defines an expanded Caribbean operating area.

## Required Puerto Rico context

Each manifest must include:

| Field | Requirement |
|---|---|
| `puerto_rico.region` | Puerto Rico region label used for federation joins. |
| `puerto_rico.municipality` | Optional municipality label if known. |
| `puerto_rico.pr_bbox_intersection` | Boolean indicating intersection with the Puerto Rico operating envelope. |

`puerto_rico.pr_bbox_intersection` must be `true` for this contract version.

## Required quality metadata

| Field | Requirement |
|---|---|
| `quality.cloud_cover_pct` | Number from `0` to `100`. |
| `quality.geometric_confidence` | Number from `0` to `1`. |
| `quality.source_reliability` | Number from `0` to `1`. |

These values describe source quality only. They do not assert anomaly confidence.

## Required lineage metadata

| Field | Requirement |
|---|---|
| `lineage.generated_by` | Process, tool, or analyst workflow that generated the manifest. |
| `lineage.processing_level` | Product processing level, for example `L1C`, `L2A`, `GRD`, or `derived-fixture`. |
| `lineage.parent_manifest_id` | Optional parent manifest identifier. |
| `lineage.notes` | Optional free-text notes. |

## Fixture-mode rule

If `synthetic` is `false`, the manifest must not use fixture, mock, or test markers in `asset.source_uri` or `asset.local_path`.

Rejected examples for `synthetic=false`:

```text
fixture://sentinel/example.tif
mock://scene/example.tif
tests/fixtures/sentinel/example.tif
/tmp/mock_scene.tif
```

Synthetic manifests are allowed for tests and fixtures, but must remain explicitly labeled with `synthetic: true`.

## Readiness behavior

The contract is fail-closed:

- Missing required fields fail validation.
- Invalid CRS fails validation.
- Invalid GeoJSON footprint shape fails validation.
- Bounding boxes outside Puerto Rico fail validation.
- Confidence values outside accepted ranges fail validation.
- `synthetic=false` with fixture/mock/test asset markers fails validation.

## Stage boundary

This contract package does not implement satellite data wiring. Runtime ingestion must not begin until this contract and its enforcement artifacts pass review.
