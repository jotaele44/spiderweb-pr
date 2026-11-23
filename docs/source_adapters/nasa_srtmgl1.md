# NASA SRTMGL1 Source Adapter

## Objective

Register NASA SRTM Global 1 arc-second v003 (SRTMGL1) for Puerto Rico, fetch its
tiles from NASA LP DAAC on demand, and measure which platform supplied each tile's
heights from the companion SRTMGL1N files.

The adapter is metadata-first. Raw tiles stay in an operator-local cache and are
never committed. The platform breakdown it feeds is in
[`../sources/dem_sources_by_platform.md`](../sources/dem_sources_by_platform.md).

## Source

| Item | Value |
| --- | --- |
| Collection | SRTMGL1 v003, CMR `C2763266360-LPCLOUD`, DOI `10.5067/MEASURES/SRTM/SRTMGL1.003` |
| Per-sample source file | SRTMGL1N v003, CMR `C2763266368-LPCLOUD` |
| Platform / instrument | STS-99 (Space Shuttle Endeavour), SRTM C-band radar interferometry |
| Acquired | 2000-02-11 to 2000-02-21 |
| Heights | metres on WGS84/EGM96 |
| Format | ZIP holding a 3601 x 3601 big-endian int16 `.hgt`; void = -32768 |
| Puerto Rico tiles | `N17W066`, `N17W067`, `N17W068`, `N18W066`, `N18W067`, `N18W068` |

The manifest is `data_sources/nasa/srtmgl1.yml`, checked against
`schemas/raster_source_manifest.schema.json`. Tile URLs, sizes and footprints were
read from CMR. The uploaded footprint snapshot (`srtm30m_bounding_boxes.json`, 14,295
features) is recorded by its sha256 and not committed; CMR lists 14,297 granules,
and the two missing (`S29W055`, `S56W072`) are outside Puerto Rico.

CMR footprints are widened by one arc-second on each side. A tile's true extent is
the whole-degree square widened by half a sample, because its edge samples sit on
the degree lines. Tiles are selected on the whole-degree square, so a box that ends
on a degree line does not pull in the neighbour.

## Authentication

LP DAAC serves the tiles only to Earthdata Login users, with a bearer token:

- **Network secret (default).** A secret for `data.lpdaac.earthdatacloud.nasa.gov`
  that the egress proxy adds to each request. The adapter then sends no credential.
- **Environment variable.** `EARTHDATA_TOKEN`, sent as `Authorization: Bearer`.

LP DAAC answers an authenticated request with a redirect to a signed CloudFront URL.
`Authorization` is dropped whenever a redirect changes host. A redirect to
`urs.earthdata.nasa.gov` means the request was not authenticated: the adapter stops
with exit code 3 and never follows the login page. Signed URLs are never recorded.

## Commands

Metadata-only plan for the Puerto Rico tiles:

```bash
python -m source_adapters.nasa_srtmgl1.cli discover --out outputs/nasa_srtmgl1/review
```

Fetch the height and source files (about 10 MB for the six tiles):

```bash
python -m source_adapters.nasa_srtmgl1.cli fetch \
  --cache-dir data/nasa_srtmgl1/cache \
  --acknowledge-no-commit
```

`--tile N18W067` (repeatable) or `--bbox W S E N` narrows the selection;
`--hgt-only` and `--num-only` fetch one product. Cached files are hashed again
rather than downloaded, unless `--force` is given.

Per-tile source composition:

```bash
python -m source_adapters.nasa_srtmgl1.cli composition --cache-dir data/nasa_srtmgl1/cache
```

Exit codes: 0 success, 2 usage or refusal, 3 Earthdata login required.

## Repository-tracked artifacts

| Artifact | Purpose |
| --- | --- |
| `data_sources/nasa/srtmgl1.yml` | Source manifest: collection, six tiles, observed composition, gaps |
| `evidence/dem_sources/srtmgl1_pr_2026-11-23/` | Live fetch receipt: per-file sha256 and the composition report |
| `source_adapters/nasa_srtmgl1/` | Adapter code |

## Repository-excluded artifacts

| Artifact | Reason |
| --- | --- |
| `*.hgt.zip`, `*.num.zip` | Raw source payloads |
| `data/nasa_srtmgl1/cache/` | Operator-local cache |
| `outputs/nasa_srtmgl1/` | Runtime review bundles |

## Observed composition (2026-11-23)

Over the six tiles' 9,906,422 land samples, 99.9788% are SRTM radar measurements.
The rest are 1,668 ASTER GDEM2 fill samples, 398 interpolated SRTM samples, 29 NGA
fill samples and 1 NED fill sample (in `N18W067`). There are no voids. Per-tile
figures are in the receipt and in the platform breakdown doc.

## Promotion rule

Use SRTMGL1 heights only when:

1. The tile's composition has been read, so the share of filled samples is known.
2. Heights stay on EGM96. No merge with PRVD02, NAVD88 or MHW products happens until
   a vertical transformation is registered with provenance.
3. They are not read as bare earth: C-band radar measures a surface between canopy
   top and ground.
4. They are not used for features smaller than a 30 m sample. The terrain pilot
   refuses such tiles unless `--allow-coarse-source` is given.
