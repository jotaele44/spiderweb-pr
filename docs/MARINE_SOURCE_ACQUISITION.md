# Marine Source Acquisition

Spiderweb's marine evidence core does not infer sensor support from a rendered
bathymetry image.  This acquisition layer establishes the source universe first,
freezes exact source responses, and only then passes whole survey/product records
to downstream analysis.

## Authoritative discovery surfaces

The initial adapters bind to two NOAA/NCEI interfaces:

1. **NCEI NEXT catalog services**
   - multibeam survey catalog:
     `https://www.ngdc.noaa.gov/next-catalogs/rest/multibeam/catalog/survey`
   - sounding survey catalog:
     `https://www.ngdc.noaa.gov/next-catalogs/rest/sounding/catalog/survey`
   - supported discovery criteria include bounding geometry, survey/platform,
     year range, page size and offset.

2. **NOS Hydrographic Survey — Surveys with BAGs feature layer**
   - service layer:
     `https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/nos_hydro_dynamic/MapServer/0`
   - the layer publishes survey polygons, `SURVEY_ID`, survey dates, platform,
     locality, BAG presence and `DOWNLOAD_URL` fields and supports pagination.

The adapters intentionally do **not** claim these two interfaces exhaust every
marine dataset family.  Lidar, topobathy lidar, side-scan/backscatter,
sub-bottom/seismic, coastal DEM and other sensor families require their own
bounded source adapters and provenance checks.

## Query identity

Every query is bound to the full request URL, including:

- source family;
- bounding box;
- start/end year when supplied;
- survey/platform filters when supplied;
- page size;
- offset;
- ArcGIS spatial relation and output CRS for NOS BAG coverage.

The NCEI bounding geometry is serialized as
`min_lon,min_lat,max_lon,max_lat`.  The NOS ArcGIS query uses the same envelope
with `inSR=4326`, `outSR=4326`, `esriSpatialRelIntersects`, all fields and
geometry returned.

## Freeze contract

Each HTTP response is frozen before interpretation with:

- final request URL;
- HTTP status;
- retrieval UTC timestamp;
- exact response byte length;
- SHA-256 of exact response bytes;
- response headers;
- exact response bytes.

`freeze_http_response()` writes the byte object and a separate JSON manifest.
The manifest does not replace the raw bytes and is never treated as byte-identical
to the source payload.

## Pagination invariants

### NCEI catalog

`fetch_all_ncei_catalog_pages()` requires:

- a stable returned `count` across every page;
- no page larger than requested;
- strictly increasing offsets;
- retained row count exactly equal to returned total count.

A zero-row response is accepted as a bounded zero only when the source returns
`count=0` successfully.  HTTP failures, invalid JSON, schema failures or count
changes fail closed and are never interpreted as no data.

### NOS BAG layer

ArcGIS pagination follows `exceededTransferLimit` and advances by the number of
whole features returned.  A non-advancing page fails closed.

## Guayama–Punta Tuna reference execution

The reference case should start from a **georegistered screenshot footprint** or
other explicitly defined AOI; no approximate bounding box is hardcoded into the
library.  This prevents an inferred map extent from silently becoming a
canonical study boundary.

Execution order:

1. establish/freeze the georegistered reference AOI;
2. query and exhaust NCEI multibeam coverage;
3. query and exhaust NCEI sounding coverage;
4. query and exhaust NOS BAG survey polygons;
5. preserve every intersecting candidate survey/product;
6. deduplicate only by stable source identity, never by name alone;
7. acquire survey-level metadata and direct/processed products;
8. bind vertical/tidal datum, sensor and acquisition lineage;
9. pass source records into `gebco.marine_evidence`;
10. test screenshot-visible morphology only where source coverage exists;
11. preserve no-coverage, derived-only and artifact-candidate states rather than
    forcing a physical-feature classification.

## Remaining source adapters

Still open after this phase:

- NOAA Digital Coast coastal/topographic lidar;
- JALBTCX coastal topobathy lidar;
- coastal DEM products and source-resolution lineage;
- side-scan/backscatter archives;
- sub-bottom and seismic-reflection archives;
- ROV/AUV imagery or navigation products;
- satellite-derived bathymetry products;
- automated acquisition of individual BAG/GSF/XYZ/metadata assets;
- authoritative vertical-datum transformation binding, such as NOAA VDatum
  where applicable.
