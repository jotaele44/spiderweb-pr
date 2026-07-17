# NOAA/NCEI Coastal DEM source integration

## Active Vector

`NOAA_NCEI_COASTAL_DEM_REPO_INTEGRATION`

## Objective

Register NOAA/NCEI coastal elevation model sources for Puerto Rico and provide a reproducible validation/acquisition path for Spiderweb PR hydro-coastal analysis.

This integration is source-manifest first. It does **not** commit NetCDF, GeoTIFF, VRT, tile-cache, or other raster runtime artifacts.

## Source basis

| Source | Use | Evidence tier | Notes |
| --- | --- | --- | --- |
| NOAA/NCEI Coastal Elevation Models catalog snapshot | DEM inventory, datum, resolution, status, PR-relevant coverage | T1 technical | Catalog page lists Puerto Rico coastal DEM entries including Arecibo, Fajardo, Guayama, Mayaguez, Ponce, Puerto Rico, and San Juan. |
| NOAA/NCEI OPeNDAP Dataset Access Form for San Juan 2015 | Concrete San Juan NetCDF endpoint and grid metadata | T1 technical metadata | Provides OPeNDAP URL, lat/lon ranges, grid shape, CRS metadata, and Band1 metadata. |

## PR-relevant catalog entries captured from source snapshot

| DEM name | Year | Vertical datum | Horizontal datum | Spatial resolution | Status | Repo action |
| --- | ---: | --- | --- | --- | --- | --- |
| Arecibo | 2007 | Mean High Water | WGS84 | 1/3 arc-second | Complete | Register as coastal DEM source candidate. |
| Fajardo | 2007 | Mean High Water | WGS84 | 1/3 arc-second | Complete | Register as coastal DEM source candidate. |
| Guayama | 2007 | Mean High Water | WGS84 | 1/3 arc-second | Complete | Register as coastal DEM source candidate. |
| Mayaguez | 2006 | Mean High Water | WGS84 | 1/3 arc-second | Complete | Register as coastal DEM source candidate. |
| Mayaguez | 2007 | Mean High Water | WGS84 | 1/3 arc-second | Complete | Register as coastal DEM source candidate. |
| Ponce | 2007 | Mean High Water | WGS84 | 1/3 arc-second | Complete | Register as coastal DEM source candidate. |
| Puerto Rico | 2017 | Puerto Rico Vertical Datum of 2002 | WGS84 | 1/9 arc-second, 1/3 arc-second | Planned in snapshot | Track as unresolved catalog-status gap until live NCEI status is checked. |
| San Juan | 2015 | Puerto Rico Vertical Datum of 2002 | WGS84 | 1/9 arc-second | Complete | Primary ingest/validation target. |

## Resolved OPeNDAP endpoints (live NGDC THREDDS regional catalog, 2026-07-16)

All six 1/3 arc-second Mean-High-Water DEMs were resolved to live endpoints and
registered in the manifest with `opendap_url`, `grid_shape`, and `elevation_var`;
each passed live DDS/DAS validation. Note the elevation grid variable differs by
vintage — most expose `Band1`, but Ponce exposes `z` (handled via the manifest's
per-dataset `elevation_var`).

| Dataset key | OPeNDAP file | Grid (lat×lon) | Elevation var |
| --- | --- | ---: | --- |
| `arecibo_2007` | `regional/arecibo_13_mhw_2007.nc` | 4861×6481 | `Band1` |
| `fajardo_2007` | `regional/fajardo_13_mhw_2007.nc` | 5941×5941 | `Band1` |
| `guayama_2007` | `regional/guayama_13_mhw_2007.nc` | 3781×7561 | `Band1` |
| `mayaguez_2006` | `regional/mayaguez_13_mhw_2006.nc` | 7561×5401 | `Band1` |
| `mayaguez_2007` | `regional/mayaguez_13_mhw_2007.nc` | 7561×5401 | `Band1` |
| `ponce_2007` | `regional/ponce_13_mhw_2007.nc` | 3781×7561 | `z` |

The PR-wide **Puerto Rico 2017** DEM was checked against the same live catalog and
is **not yet published** there (GAP_001 remains open).

## San Juan 2015 OPeNDAP target

```text
https://www.ngdc.noaa.gov/thredds/dodsC/regional/san_juan_19_prvd02_2015.nc
```

Captured metadata:

| Field | Value |
| --- | --- |
| Dataset key | `san_juan_19_prvd02_2015` |
| Format | NetCDF via THREDDS/OPeNDAP |
| CRS grid mapping | latitude/longitude |
| Horizontal datum | WGS84 |
| Vertical datum | Puerto Rico Vertical Datum of 2002 |
| Latitude range | `18.379984568` to `18.540014408` |
| Longitude range | `-66.230015432` to `-65.909986616` |
| Grid shape | `lat=5185`, `lon=10369` |
| Band | `Band1` / `Float32 Band1[lat][lon]` |

## Integrity check

The OPeNDAP form snapshot reports `Band1 actual_range: 0.0, 0.0`. This was treated as a contradiction flag, not as an elevation fact. **Resolved 2026-07-16:** a live strided raster sample (stride 60) returned `min -903.33 / max 120.99` with 0% nodata and `flat_zero_flag=false`, confirming the `0.0,0.0` was an OPeNDAP-form metadata artifact rather than the raster. San Juan is now `source_raster_validated` (GAP_003 closed). The QA path used:

1. Open the dataset through OPeNDAP or an official downloaded NetCDF.
2. Confirm CRS, grid shape, bounds, and datum.
3. Compute sampled and/or full `Band1` min/max.
4. Compute nodata percentage.
5. Confirm the raster contains non-flat elevation/bathymetry values.
6. Write only QA reports to `outputs/`; do not commit raster products.

## Spiderweb layer placement

| Layer family | Use |
| --- | --- |
| `02_HYDROLOGY_KARST` | Coastal outlet gradients, nearshore bathy-topo transition, hydro-corridor context. |
| `05_AIRSPACE_MARITIME` | Harbor approach, coastal shelf, maritime/bathy context. |
| `10_REFERENCE` | NOAA/NCEI source registry and source lineage. |

## Scoring rule

These sources may increase confidence for hydro/coastal context, but they do not independently prove subsurface access, covert infrastructure, or UAP/USO claims. Use them only as T1 terrain/bathymetry reference evidence.

## Reproducible validation command

```bash
python scripts/acquire/noaa_ncei_opendap.py \
  --manifest data_sources/noaa/ncei_coastal_dems.yml \
  --dataset san_juan_19_prvd02_2015 \
  --metadata-only \
  --output outputs/noaa_ncei/san_juan_19_prvd02_2015_metadata_check.json
```

Optional raster sampling requires an environment with `xarray` and a compatible NetCDF/OPeNDAP backend:

```bash
python scripts/acquire/noaa_ncei_opendap.py \
  --manifest data_sources/noaa/ncei_coastal_dems.yml \
  --dataset san_juan_19_prvd02_2015 \
  --sample-raster \
  --stride 50 \
  --output outputs/noaa_ncei/san_juan_19_prvd02_2015_sample_qa.json
```

## Gap queue

| Gap ID | Gap | Closure path | Status |
| --- | --- | --- | --- |
| `NOAA_NCEI_DEM_GAP_001` | Live status of broader `Puerto Rico 2017` DEM is unresolved from the static snapshot. | Query current NCEI/THREDDS catalog and update manifest. | **Open** — checked 2026-07-16, PR-wide 2017 DEM not yet in the THREDDS regional catalog. |
| `NOAA_NCEI_DEM_GAP_002` | PR regional DEM URLs other than San Juan are not yet resolved into direct OPeNDAP/NetCDF endpoints. | Resolve detail pages and register direct data URLs. | **Closed 2026-07-16** — all six MHW DEMs resolved + live-validated. |
| `NOAA_NCEI_DEM_GAP_003` | San Juan `Band1 actual_range` contradiction not yet resolved. | Run live raster sampling/full minmax validation. | **Closed 2026-07-16** — live sample min/max confirms real terrain. |
| `NOAA_NCEI_DEM_GAP_004` | No derived coastal products generated yet. | Build downstream products only after raster QA passes. | Open — source raster QA now passes; derivatives still not generated (out of scope). |

## Completion state

Source registration, schema guardrails, and the validation script are in place. As of 2026-07-16 all seven live-available PR coastal DEMs (San Juan 2015 + six 1/3 arc-second MHW DEMs) are resolved to live OPeNDAP endpoints and metadata-validated; San Juan is raster-sampled and `source_raster_validated`. Derived coastal products are still not generated (GAP_004).
