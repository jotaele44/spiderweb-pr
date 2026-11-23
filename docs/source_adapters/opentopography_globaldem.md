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

SRTMGL1 and NASADEM heights are on EGM96. The vertical datums of COP30 and AW3D30
were not stated in the metadata checked, so the catalog records them as
`undeclared`, and the merge policy holds any selection that includes them for review.
