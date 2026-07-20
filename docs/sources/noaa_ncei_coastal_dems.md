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
is **not yet published** there. PR-wide coverage has instead been sourced from the
NOAA Coastal LiDAR PDS CUDEM (see next section), which **mitigates GAP_001**.

## PR-wide CUDEM base layer (added 2026-07-20)

The PR-wide gap left by the unpublished *Puerto Rico 2017* THREDDS DEM is filled by
NOAA's **Continuously Updated Digital Elevation Model (CUDEM), ninth arc-second
Bathymetric-Topographic tiles for Puerto Rico** (`m9525`, 2022), registered as
`puerto_rico_cudem_ninth_9525`.

| Field | Value |
| --- | --- |
| Dataset key | `puerto_rico_cudem_ninth_9525` |
| Product | NCEI CUDEM ninth arc-second Topobathy — Puerto Rico (`m9525`) |
| Year | 2022 (created 2022-06-03, published 2022-06-11) |
| Spatial resolution | 1/9 arc-second (~3.09 m) |
| Vertical datum | Puerto Rico Vertical Datum of 2002 (PRVD02) |
| Horizontal datum / CRS | NAD83 (EPSG:4269) |
| Bounds (W/E/S/N) | `-68.00` / `-65.25` / `17.75` / `18.75` |
| Format / access | GeoTIFF tiles via AWS S3 (NOAA Coastal LiDAR PDS) + bulk download |
| Tiles | 25 (`ncei19_n<lat>_w<lon>_2022v<version>.tif`), VRT `NCEI_ninth_Topobathy_PuertoRico_EPSG-4269.vrt`, ~4.7 GB |
| URL list | `urllist9525.txt` |
| Citation | Amante et al. 2023 (CUDEM) |

**Why the ninth (1/9) arc-second and not the third (1/3, `m9524`):** in NCEI's CUDEM
design only the ninth arc-second tier fully integrates land **topography** with
bathymetry; the third arc-second tier is bathymetry-leaning. The ninth tier also
shares the **PRVD02** vertical datum of the existing primary `san_juan_19_prvd02_2015`,
so the two layers compose consistently (San Juan remains a higher-detail local inset;
the CUDEM is the island-wide base).

**Access note:** unlike the San Juan and MHW DEMs, this CUDEM is distributed as
GeoTIFF on S3 rather than through the NGDC THREDDS `regional/*.nc` catalog, so the
manifest entry carries `source_url` / `s3_prefix` / `url_list` instead of an
`opendap_url` (the schema's `opendap_url` is optional). No raster binaries are
committed. Live raster QA (min/max, nodata) is still `pending_live_sample`, so the
dataset sits at `source_metadata_registered` (not yet `source_raster_validated`).

> **Reprojection required before terrain screening (GAP_005).** These CUDEM tiles are
> **geographic — EPSG:4269 (NAD83), pixel size ≈ 2.78e-5° (1/9 arc-second)**. The
> rasterio tile-screening tools (`tools/pr_dem_one_tile_pilot.py`,
> `tools/pr_dem_batch_runner.py`) currently assume a **projected, metre-based** CRS:
> they derive the downsample factor from `target_resolution_m / native` (a ~0.25° tile
> collapses toward 1×1, so `np.gradient` fails), and compute slope and pixel area
> directly from `src.transform` units. Downloaded CUDEM tiles must therefore be
> **reprojected to a metric CRS** (e.g. UTM 19N / EPSG:32619) — or those tools made
> CRS-aware — before being routed through this tooling. Tracked as `NOAA_NCEI_DEM_GAP_005`.

**Higher-resolution alternative (future option, not adopted here):** the NOAA Data
Access Viewer also lists raw LiDAR **point-cloud** collections for the PR area
(USGS/USACE/NOAA-NGS, up to hundreds of billions of points). These offer sub-meter
detail but require a new LAS/LAZ ingestion path (e.g. PDAL/laspy → DEM) that does not
exist in this repo today; they are recorded here as a future high-resolution option
rather than integrated.

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
| `NOAA_NCEI_DEM_GAP_001` | Live status of broader `Puerto Rico 2017` DEM is unresolved from the static snapshot. | Query current NCEI/THREDDS catalog and update manifest. | **Mitigated 2026-07-20** — the 2017 THREDDS DEM is still unpublished, but PR-wide 1/9 arc-second coverage is now provided by the CUDEM `puerto_rico_cudem_ninth_9525` (`m9525`, 2022). |
| `NOAA_NCEI_DEM_GAP_002` | PR regional DEM URLs other than San Juan are not yet resolved into direct OPeNDAP/NetCDF endpoints. | Resolve detail pages and register direct data URLs. | **Closed 2026-07-16** — all six MHW DEMs resolved + live-validated. |
| `NOAA_NCEI_DEM_GAP_003` | San Juan `Band1 actual_range` contradiction not yet resolved. | Run live raster sampling/full minmax validation. | **Closed 2026-07-16** — live sample min/max confirms real terrain. |
| `NOAA_NCEI_DEM_GAP_004` | No derived coastal products generated yet. | Build downstream products only after raster QA passes. | Open — source raster QA now passes; derivatives still not generated (out of scope). |
| `NOAA_NCEI_DEM_GAP_005` | CUDEM `m9525` tiles are geographic (EPSG:4269); the `pr_dem_*` tile-screening tools assume a projected metre-based CRS (downsample factor, slope, pixel area). | Reproject tiles to a metric CRS (e.g. UTM 19N / EPSG:32619) before screening, or make the tools CRS-aware. | Open — flagged 2026-07-20 during CUDEM registration; fix is in the `pr_dem_*` tooling, out of scope for this source-registration change. |

## Completion state

Source registration, schema guardrails, and the validation script are in place. As of 2026-07-16 all seven live-available PR coastal DEMs (San Juan 2015 + six 1/3 arc-second MHW DEMs) are resolved to live OPeNDAP endpoints and metadata-validated; San Juan is raster-sampled and `source_raster_validated`. As of 2026-07-20 the PR-wide CUDEM ninth arc-second base layer (`puerto_rico_cudem_ninth_9525`, `m9525`, 2022) is registered from provider metadata (GeoTIFF/S3), mitigating GAP_001; its live raster QA is pending. Derived coastal products are still not generated (GAP_004).
