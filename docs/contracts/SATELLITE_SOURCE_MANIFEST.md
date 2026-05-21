# Satellite Source Manifest Contract

Schema ID: `satellite_source_manifest`  
Schema version: `1.0`  
JSON Schema dialect: Draft-07  
File: `schemas/satellite_source_manifest.schema.json`

---

## Purpose

Every satellite or remote-sensing raster ingested by the Spiderweb pipeline
must be accompanied by a **satellite source manifest** — a JSON document that
declares the asset's origin, geometry, quality metrics, and processing lineage.

The contract is **fail-closed**: any record that violates the schema is
rejected before it can enter the pipeline. The fixture-mode rule additionally
prevents real-data manifests from accidentally referencing fixture, test, or
mock assets.

Manifests are written by the ingestion stage and validated by `SchemaValidator`
before any downstream consumer (EarthGPT tile fetch, GEBCO overlay, PRII
readiness engine) reads the asset.

## Scope and Non-Goals

This contract covers source metadata and provenance. A Stage 3 producer —
`satellite_ingest.py`, wired into `run_all.py --ingest-satellite` — now
generates and validates these manifests from a synthetic catalog or a STAC
ItemCollection. The fixture-mode rule and the Puerto Rico envelope are
enforced at validation time; rejected scenes are routed to a `rejected/`
directory rather than entering the pipeline.

Still out of scope:

- No raster tiling, download, or image-processing pipeline — manifests
  reference assets; they do not fetch or decode them.
- No producer repository alignment.
- Live STAC API querying is supported structurally (`--sat-source stac`
  with an HTTP(S) URL and an optional `SAT_STAC_TOKEN` bearer token) but is
  exercised only against local fixtures in CI.

---

## Fixture-Mode Rule

The `synthetic` field is a first-class contract field.

| `synthetic` | Effect |
|-------------|--------|
| `true` | No URI/path restrictions — fixture URIs like `s3://fixture-bucket/…` are allowed. Use this in all tests and development environments. |
| `false` | The strings `fixture`, `test`, and `mock` are **banned** (case-insensitive) in both `asset.source_uri` and `asset.local_path`. Validation fails if either value matches the pattern `(?i)(fixture\|test\|mock)`. |

This rule is implemented as a Draft-07 `if/then` constraint at the top level
of the schema. It fires whenever `synthetic` is explicitly `false`; it is
silently skipped when `synthetic` is `true`.

---

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `manifest_id` | string | yes | Unique identifier for this manifest (e.g. `SAT-PR-2024-001`). |
| `schema_version` | string | yes | Contract version — must match pattern `^\d+\.\d+$` (e.g. `"1.0"`). |
| `producer` | string | yes | System or process that created this manifest (e.g. `"spiderweb-sat-ingest-v1"`). |
| `created_at` | string | yes | ISO 8601 timestamp of manifest creation. |
| `synthetic` | boolean | yes | `true` for fixture/test data; `false` for production rasters. Drives the fixture-mode rule. |
| `notes` | string\|null | no | Free-text annotation. |
| `source` | object | yes | Data origin — see [`source` Object](#source-object). |
| `acquisition` | object | yes | Acquisition metadata — see [`acquisition` Object](#acquisition-object). |
| `asset` | object | yes | File reference — see [`asset` Object](#asset-object). |
| `geometry` | object | yes | Spatial extent — see [`geometry` Object](#geometry-object). |
| `puerto_rico` | object | yes | Puerto Rico region classification — see [`puerto_rico` Object](#puerto_rico-object). |
| `quality` | object | yes | Quality metrics — see [`quality` Object](#quality-object). |
| `lineage` | object | yes | Processing lineage — see [`lineage` Object](#lineage-object). |

`additionalProperties: true` — extra top-level fields are permitted and ignored.

---

## `source` Object

Required fields: `provider`, `collection`, `platform`, `instrument`.

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | Data provider organisation (e.g. `"ESA"`, `"NASA"`, `"NOAA"`). |
| `collection` | string | Dataset collection name (e.g. `"sentinel-2-l2a"`, `"landsat-9-c2l2"`). |
| `platform` | string | Satellite platform (e.g. `"Sentinel-2A"`, `"Landsat 9"`). |
| `instrument` | string | Sensor/instrument name (e.g. `"MSI"`, `"OLI-TIRS"`). |

---

## `acquisition` Object

Required fields: `acquired_at`, `processed_at`, `license`.

| Field | Type | Description |
|-------|------|-------------|
| `acquired_at` | string | ISO 8601 scene acquisition timestamp. |
| `processed_at` | string | ISO 8601 timestamp of analysis-ready dataset processing. |
| `license` | string | Data license or terms of use (e.g. `"Copernicus Sentinel Data Terms of Use"`). |

---

## `asset` Object

Required fields: `checksum_sha256`, `media_type`, and **at least one of** `source_uri` or `local_path`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_uri` | string | one-of | Remote URI of the raster asset (S3, GCS, HTTPS, etc.). |
| `local_path` | string | one-of | Absolute path to a locally cached copy. |
| `checksum_sha256` | string | yes | Lowercase hex SHA-256 of the asset file. Must match `^[0-9a-f]{64}$`. |
| `media_type` | string | yes | MIME type (e.g. `"image/tiff"`, `"image/jp2"`, `"application/geo+json"`). |

At least one of `source_uri` or `local_path` must be present (enforced via
`anyOf`). Both may be present simultaneously.

When `synthetic=false`, `source_uri` and `local_path` must not contain
the substrings `fixture`, `test`, or `mock` (case-insensitive).

---

## `geometry` Object

Required fields: `crs`, `footprint`, `bbox`.

| Field | Type | Description |
|-------|------|-------------|
| `crs` | string | Coordinate reference system. **Must be `"EPSG:4326"`** (enum, no other value accepted). |
| `footprint` | object | GeoJSON Polygon — see below. |
| `bbox` | array[4] | Bounding box `[west, south, east, north]` — must fall within the Puerto Rico operating envelope. |

### `footprint` Sub-Object

| Field | Type | Constraint |
|-------|------|-----------|
| `type` | string | **Must be `"Polygon"`** (enum). |
| `coordinates` | array | GeoJSON ring array, minItems 1. Each coordinate pair is validated against PR bounds. |

### Puerto Rico Operating Envelope

All coordinates (footprint and bbox) are validated against the Puerto Rico
archipelago bounding box:

| Axis | Minimum | Maximum |
|------|---------|---------|
| Longitude (west/east) | -68.2° | -65.1° |
| Latitude (south/north) | 17.8° | 18.7° |

Source packages outside this envelope are rejected for Puerto Rico federation
workflows.

---

## `puerto_rico` Object

Required field: `region`.

| Field | Type | Allowed values / Notes |
|-------|------|------------------------|
| `region` | string enum | `mainland`, `vieques`, `culebra`, `mona`, `isla_grande`, `full_island` |
| `municipality` | string\|null | optional — municipality name if known |

`mainland` covers the main island. `full_island` is used for whole-island mosaics.

---

## `quality` Object

Required fields: `cloud_cover_pct`, `geometric_confidence`, `source_reliability`.

| Field | Type | Range / Values | Description |
|-------|------|----------------|-------------|
| `cloud_cover_pct` | number | 0 – 100 | Estimated cloud cover as a percentage of scene area. |
| `geometric_confidence` | number | 0 – 1 | Confidence in positional accuracy; 1.0 = highest. |
| `source_reliability` | string enum | `high`, `medium`, `low`, `unverified` | Overall reliability assessment of the data source. |

---

## `lineage` Object

Required field: `processing_pipeline`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `processing_pipeline` | string | yes | Name of the pipeline that produced this manifest (e.g. `"spiderweb-sat-ingest-v1"`). |
| `pipeline_version` | string\|null | no | Semantic version of the pipeline. |
| `derived_from` | array of strings | no | Parent manifest IDs this asset was derived from. |

---

## Minimal Valid Example

```json
{
  "manifest_id":    "SAT-PR-2024-001",
  "schema_version": "1.0",
  "producer":       "spiderweb-pipeline",
  "created_at":     "2024-03-14T14:32:00Z",
  "synthetic":      true,
  "source": {
    "provider":   "ESA",
    "collection": "sentinel-2-l2a",
    "platform":   "Sentinel-2A",
    "instrument": "MSI"
  },
  "acquisition": {
    "acquired_at":  "2024-03-14T14:32:00Z",
    "processed_at": "2024-03-15T02:00:00Z",
    "license":      "Copernicus Sentinel Data Terms of Use"
  },
  "asset": {
    "source_uri":      "s3://fixture-bucket/pr/sentinel2/2024-03-14.tif",
    "checksum_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "media_type":      "image/tiff"
  },
  "geometry": {
    "crs": "EPSG:4326",
    "footprint": {
      "type": "Polygon",
      "coordinates": [[
        [-67.0, 18.0], [-66.0, 18.0],
        [-66.0, 18.5], [-67.0, 18.5],
        [-67.0, 18.0]
      ]]
    },
    "bbox": [-67.0, 18.0, -66.0, 18.5]
  },
  "puerto_rico": {"region": "mainland"},
  "quality": {
    "cloud_cover_pct":      12.5,
    "geometric_confidence": 0.92,
    "source_reliability":   "high"
  },
  "lineage": {"processing_pipeline": "spiderweb-sat-ingest-v1"}
}
```

Note: `synthetic: true` allows `fixture-bucket` in the URI. Set
`synthetic: false` for any real production manifest and ensure neither
`source_uri` nor `local_path` contains `fixture`, `test`, or `mock`.

---

## Validation

**Programmatic validation** — use `SchemaValidator` from `schema_validation.py`:

```python
from schema_validation import SchemaValidator
v = SchemaValidator()
result = v.validate(manifest_dict, "satellite_source_manifest")
if not result["valid"]:
    print(result["errors"])
```

The schema is auto-loaded by `SchemaValidator._load_schemas()` from the
`schemas/` directory — no registration step required.

**Test coverage** — `tests/test_satellite_source_manifest_schema.py` contains
17 tests that exercise the required fields, all enum/range constraints, the
fixture-mode rule, and the Puerto Rico coordinate bounds.

Run with:

```bash
python -m pytest tests/test_satellite_source_manifest_schema.py -v
```
