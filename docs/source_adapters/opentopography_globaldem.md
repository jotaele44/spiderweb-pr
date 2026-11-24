# OpenTopography Global DEM Adapter

## Objective

Fetch clipped global DEMs for Puerto Rico from OpenTopography's
`/API/globaldem`, so terrain from separate spaceborne platforms can be compared.
Each demtype is tied to its entry in the DEM platform catalog
([`../sources/dem_sources_by_platform.md`](../sources/dem_sources_by_platform.md)).

| demtype | Catalog entry | Platform |
| --- | --- | --- |
| `SRTMGL1` | `nasa_srtmgl1_v003` | STS-99, C-band radar interferometry (2000) |
| `NASADEM` | `nasa_nasadem_hgt_v001` | The same Shuttle flight, reprocessed |
| `COP30` | `copernicus_glo30_dem` | TanDEM-X, X-band radar interferometry (2011-2015) |
| `AW3D30` | `jaxa_aw3d30` | ALOS PRISM, optical stereo (2006-2011) |

SRTMGL1 and NASADEM share one acquisition, so they do not corroborate each other.
COP30 and AW3D30 are independent of both. OpenTopography does not serve the SRTMGL1N
per-sample source files; use the LP DAAC adapter (`docs/source_adapters/nasa_srtmgl1.md`)
for SRTM composition.

The configuration is `data_sources/opentopography/globaldem.yml`.

## API key

OpenTopography's OpenAPI document (`https://portal.opentopography.org/apidocs/openapi.json`)
declares `API_Key` as a required **query** parameter, with no header scheme. The
key is read from `OPENTOPOGRAPHY_API_KEY`, or `OpenTopography_API_KEY` (the name
Skywatcher's GEBCO fetcher also reads).

Because the key travels in the URL:

- every URL the adapter prints, logs or writes to provenance has `API_Key=REDACTED`;
- errors are re-raised without the original exception, which carries the full URL;
- a response that is not a GeoTIFF (for example an XML error page) is refused and
  not saved.

## Commands

Show the requests that would be made (key redacted):

```bash
python -m source_adapters.opentopography_globaldem.cli plan
```

Fetch one or more demtypes for the configured AOI:

```bash
python -m source_adapters.opentopography_globaldem.cli fetch \
  --demtype COP30 \
  --cache-dir data/opentopography/cache \
  --acknowledge-no-commit
```

`--bbox W S E N` overrides the AOI. Exit codes: 0 success; 2 usage, refusal or
missing key; 3 key refused (HTTP 401 or 403); 4 other request failure.

## Repository policy

GeoTIFFs stay in `data/opentopography/cache/`, which is git-ignored, with a
`provenance.json` of sha256, size and the redacted request. Only the configuration
and code are tracked.

## Datums

| demtype | Vertical datum | Basis |
| --- | --- | --- |
| `SRTMGL1` | EGM96 (EPSG 5773) | NASA CMR; OpenTopography catalogue |
| `NASADEM` | EGM96 (EPSG 5773) | NASA CMR; OpenTopography catalogue |
| `COP30` | EGM2008 (EPSG 3855) | ESA Copernicus DEM Product Handbook issue 5.0, page 13; OpenTopography catalogue |
| `AW3D30` | EGM96 (EPSG 5773) | OpenTopography catalogue and its AW3D30_E description; JAXA's product description could not be retrieved (HTTP 404) |

OpenTopography gives the datum in each dataset's structured `spatialCoverage` fields
("Vertical Coordinates", "EPSG (Vertical)"), not in the description text. None of the
fetched GeoTIFFs states a vertical CRS (all are EPSG:4326 only), and neither does ESA's
own COP30 tile. Over Puerto Rico, EGM2008 and EGM96 differ by -0.95 to +1.09 m. Details
and sources: `docs/sources/dem_sources_by_platform.md` and
`evidence/dem_sources/vertical_datums_2026-11-24/datum_check.json`.

## Observed fetches

All three were fetched for the Puerto Rico AOI through this adapter. Each recorded
request reads `API_Key=REDACTED`, and the key appears in no receipt file. No sample
in any file is nodata (NASADEM declares -32768 but never uses it), and no file
declares a vertical CRS: all three are EPSG:4326 only.

| demtype | File | Grid | Heights |
| --- | --- | --- | --- |
| COP30 (2026-11-23) | 43,254,754 B, sha256 `c94a3c7060d64a2f…` | float32, 9,900 x 2,520 at 1 arc-second, pixel-is-point | -8.84 to 1,328.76 m |
| AW3D30 (2026-11-24) | 11,115,033 B, sha256 `8372dac38f6b56e1…` | int16, 9,900 x 2,520 at 1 arc-second, pixel-is-area | -104 to 1329 m |
| NASADEM (2026-11-24) | 10,951,851 B, sha256 `3f6c0ea5d10e839d…` | int16, 9,900 x 2,520 at 1 arc-second, pixel-is-area (tag), on SRTM sample lines | -47 to 1327 m |

Receipts: `evidence/dem_sources/cop30_pr_2026-11-23/`,
`evidence/dem_sources/aw3d30_pr_2026-11-24/` and
`evidence/dem_sources/nasadem_pr_2026-11-24/`.

**Grid registration.** SRTMGL1, NASADEM and COP30 samples fall on whole
arc-seconds. AW3D30 is pixel-is-area: its sample centres sit half an arc-second east
and south of the others (about 21 m diagonally). Comparing AW3D30 sample for sample
with SRTM by index would compare shifted points; the comparison below interpolates
SRTM to AW3D30's own centres.

## Four spaceborne sources compared (2026-11-24)

Differences from SRTMGL1 over 9,887,061 SRTM land samples (SRTMGL1N
above 10). Receipt: `evidence/dem_sources/spaceborne_pr_2026-11-24/comparison.json`.

| Minus SRTMGL1 | Samples | Median | Mean | Std dev | MAD | 95th pct abs | Within 1 m | Within 5 m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NASADEM | 9,887,061 | -2 m | -1.742 m | 1.754 m | 1 m | 4 m | 41.059% | 98.528% |
| COP30 | 9,887,061 | 1.132 m | 1.523 m | 4.854 m | 2.824 m | 10.35 m | 19.805% | 73.054% |
| AW3D30 | 9,858,637 | 0.5 m | 0.937 m | 4.602 m | 2.001 m | 9.5 m | 30.661% | 79.798% |

NASADEM, reprocessed from the same 2000 Shuttle flight, agrees with SRTMGL1 about
2.7 times more tightly than COP30 (TanDEM-X) or AW3D30 (ALOS PRISM). That is what the
catalog's shared acquisition root predicts. NASADEM also sits about 2 m lower than
SRTMGL1 on average.

At the Cerro de Punta summit (GNIS 1609905, 18.172281, -66.5916862):

| Source | Height | Vertical datum |
| --- | --- | --- |
| SRTMGL1 | 1325 m | EGM96 |
| NASADEM | 1323 m | EGM96 (CMR) |
| COP30 | 1328.29 m (1329.05 m on EGM96) | EGM2008 |
| AW3D30 | 1328 m | EGM96 |

TheHub's CUDEM reader gives 1,322.7 m (PRVD02) at the same point. Here EGM2008 sits
0.76 m above EGM96, so COP30 reads 1,329.05 m on SRTM's datum. The sources still differ
in epoch (2000, 2006-2011, 2011-2015) and surface (C-band and X-band radar, optical
first surface), so these differences are not terrain change. The comparison table
above uses the heights as published; putting COP30 on EGM96 moves its median from
1.14 m to 1.38 m and leaves its spread unchanged.
