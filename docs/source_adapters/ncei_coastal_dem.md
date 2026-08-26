# NCEI Coastal DEM Source Adapter

## Objective

Use NOAA/NCEI Coastal Elevation Models and CUDEM metadata as an on-demand,
provenance-first source adapter for Puerto Rico coastal bathymetric-topographic
context.

This adapter is a metadata and fetch-planning layer. It does not commit raw DEM
rasters and it does not assert anomaly conclusions.

## Source families

| Source family | Scope | Access mode |
| --- | --- | --- |
| `NCEI_REGIONAL_DEM` | Named regional NetCDF DEMs such as San Juan, Arecibo, Fajardo, Guayama, Mayaguez, and Ponce | THREDDS/fileServer |
| `NOAA_CUDEM_TILE` | Puerto Rico bathymetric-topographic CUDEM tiles at 1/9 and 1/3 arc-second resolution | NOAA/NCEI metadata and access services |

## Commands

Metadata-only review of all registered Puerto Rico records:

```bash
python -m source_adapters.ncei_coastal_dem.cli discover \
  --aoi puerto_rico \
  --include-static-registry \
  --include-live-catalogs \
  --include-acquisition-context-leads \
  --out outputs/ncei_coastal_dem/review_bundle \
  --metadata-only
```

Explicit local fetch of one DEM payload:

```bash
python -m source_adapters.ncei_coastal_dem.cli fetch \
  --dataset san_juan_19_prvd02_2015 \
  --cache-dir data/ncei_coastal_dem/cache \
  --acknowledge-no-commit
```

## Repository-tracked artifacts

| Artifact | Policy | Purpose |
| --- | --- | --- |
| `data/ncei_coastal_dem/registry/ncei_coastal_dem_priority_datasets.csv` | Track | Small priority dataset ledger |
| `data/ncei_coastal_dem/registry/ncei_coastal_dem_registry.schema.json` | Track | Registry contract |
| `schemas/ncei_coastal_dem_source_manifest.schema.json` | Track | Manifest output contract |
| `schemas/ncei_coastal_dem_coverage_report.schema.json` | Track | Coverage output contract |
| `tests/fixtures/ncei_coastal_dem/*` | Track | Offline CI fixtures |

## Repository-excluded artifacts

| Artifact | Policy | Reason |
| --- | --- | --- |
| Raw NetCDF DEMs (`*.nc`) | Exclude | Large, regenerable source payload |
| GeoTIFF/VRT/raster derivatives | Exclude by default | Large runtime products |
| `data/ncei_coastal_dem/cache/` | Exclude | Operator-local cache |
| `data/ncei_coastal_dem/raw/` | Exclude | Operator-local raw staging |
| `outputs/ncei_coastal_dem/*` | Exclude except `.gitkeep` | Runtime review bundles |

## Datum policy

The adapter enforces declared horizontal and vertical datums in the priority
registry. Mixed vertical datums are not merged into one surface unless a later
patch supplies explicit vertical-transformation metadata.

Known registry examples include:

- San Juan 2015: PRVD02, WGS84, 1/9 arc-second.
- Arecibo/Fajardo/Guayama/Mayaguez/Ponce 2007-era regional DEMs: Mean High
  Water, WGS84, 1/3 arc-second.
- Puerto Rico CUDEM tile products: source-dependent lineage; keep separate from
  older regional DEMs until reviewed.

## Acquisition/procurement context guardrail

USGS GPSC/GPSC3 and LBS award records may explain how some elevation products
were acquired, including the `PR_USVI_2018_D18 USGS_LBS_V1.3` lead from the
pasted USAspending query output. These records are not source DEM rasters and
are not authoritative DEM metadata.

SpiderWeb may retain only non-authoritative `acquisition_context_refs` when a
record is directly tied to a DEM/LIDAR source. Procurement normalization belongs
to `moneysweep-pr`. Hub-level correlation should join SpiderWeb spatial outputs
with MoneySweep procurement outputs only after both producers emit canonical
packages.

## Promotion rule

Promote DEM-derived outputs only when:

1. Source URL, access method, resolution, horizontal datum, and vertical datum are declared.
2. Raw payloads remain local and uncommitted.
3. Any downloaded payload receives SHA-256 provenance.
4. Mixed vertical datums are kept as separate layers or blocked for review.
5. No output uses confirmed-anomaly language.
6. Procurement leads remain contextual until source metadata corroborates them.
