# Live NOAA catalogs and exact AOI recommendations — 2026-09-13

PR #357; continuation of 5a44c692d0700bb71cdd6d4835702995b21ea26a.
Status: DRAFT / OPEN. No merge, deployment, production registry activation or raster acquisition.

## Executed scope

Two real NOAA-published DEM Collection/ItemCollection/URL-list snapshots were
retrieved, hash-frozen, converted and exercised through the production planner,
recommendation parser and React dataset selector. The denominator is these two
snapshots, NOT all Puerto Rico datasets or all NOAA collections. No cross-source
measurement equivalence or valid-observation coverage is certified.

The prior local-container DNS failure was bypassed using an isolated, network-enabled
Node/Python runtime on the user's existing Spiderweb Floot project. Only temporary
scratch files and archival/code-transfer assets were written. The Floot app source,
database, configuration and deployment were not changed. Source HTTP requests used
identity encoding, rejected redirects, checked response lengths and preserved full
header/time/hash receipts. Frozen inputs were reused after every conversion failure.

## Raw input receipts

All six responses were HTTP 200. Size is original uncompressed bytes.

| Snapshot member | Bytes | SHA-256 |
|---|---:|---|
| m9101 Collection | 1054402 | c400dc09cf6b64ea55231a744295f2451d21f0af3c43e894c912c33b92b0f55a |
| m9101 ItemCollection | 39788266 | 5fc6efec7c1ee5dd16354ae42caecfdca307ebe2733934a5ca0b3e9d1626f69e |
| m9101 URL list | 1303947 | 4b83e4cfd2d4739489fcf2b64b6315806adf37b42e6f16d8f7256d3076318a7d |
| m8571 Collection | 689868 | ecec066c44d2c92cdda25057274da574b7e68f42ac857dabe24e1e7ac3e9b0e1 |
| m8571 ItemCollection | 12711566 | 9737a51bea070c74b4442434c1f569b23c5f947a5f8264bb9a5ecf12055a06af |
| m8571 URL list | 859165 | c35e0b2c37677f7c959ff932e68a027bed7789871b238fb7557da57a7745cb26 |

Retrieval window: 2026-09-13T17:00:51.957Z through 2026-09-13T17:01:30.742Z.
Exact URLs, timestamps and headers are in the archive retrieval receipts. The two
source prefixes remain explicitly allowlisted in configs/aoi_catalog_sources.json.

## Complete catalog accounting

- m9101: 4,399 data files and 4,399 item metadata URLs, plus four structural URLs
  and ten declared auxiliaries: 8,812 = 4,399 + 4,399 + 4 + 10.
- m8571: 2,823 data files and 2,823 item metadata URLs, plus four structural URLs
  and four declared auxiliaries: 5,654 = 2,823 + 2,823 + 4 + 4.
- Combined file-footprint denominator: 7,222 = 4,399 + 2,823.

Both snapshots have zero unexplained URL rows and zero item-self/data-URL duplicates.
Collection-to-item links and STAC-to-data-URL membership have A_ONLY = B_ONLY =
SYMMETRIC_DIFFERENCE = empty. INTERSECTION and UNION each contain the full respective
4,399 or 2,823 member set. Every original URL line and its classification is archived.
These are publication/file-inventory bindings, not evidence of independent measurements.

## Real schema adaptations and identity adjudication

All 7,222 published items omit the optional collection member and their sole
assets omit optional roles. The previous strict profile rejected them. A new
explicit noaa_cog_single_asset_v1 profile allows missing fields only when exact
Collection item links bind item self links, and the single COG asset has the exact
published media type, valid grid metadata and independent URL-list membership.
Explicit conflicting/null collection IDs, wrong links, non-data roles, unsupported
media/grid values, missing URLs and multi-asset ambiguity still fail closed.

m8571 has 261 repeated-raw-ID groups involving 524 records; there are 263 excess
raw-ID occurrences. These records have distinct collection-linked self URLs and
distinct data URLs. They were NOT dropped, merged or assigned filename identity.
The configured collection_linked_self_url scope qualifies asset identity with the
exact linked source URI and asset key. Raw IDs and every collision member remain
preserved as NONCANONICAL_DUPLICATE_IDS. Default item_id mode still rejects duplicates;
repeated self URLs or data URLs remain blocked in every mode. This establishes source
manifestation identity, not equality or independence of terrain observations.

m9101's complete URL list also revealed two additional block VRTs absent from the
previous excerpt-based inventory. Its explicit auxiliary denominator is now ten.
m8571's four auxiliaries were established from its own frozen bytes, not inherited.

Derivative paths now bind source snapshot, actual converter-source hashes, Python
runtime/serialization and output catalog hash. A changed converter cannot overwrite
a prior derivative under an unchanged raw-snapshot identity.

## Normalized catalog bindings

m9101 catalog SHA-256:
59b474f5245d19353fad8fffc2db1eeece13674847cc1ac82672439aa99f9489

m9101 derivative version:
dd3a976154fad2b62fb0712bd863b72f78a6413589e0ce3e3f8e8559b538617c

m8571 catalog SHA-256:
813efa19708488a89ebf5cf5800bcbcbd0a35b82dcc50f4e3e87a1a764ca7a10

m8571 derivative version:
fd96fa1bfec388e22acd57d46db70139145ea446280f24b3eec782c348d03a05

Relative paths are registry/aoi/catalogs/<dataset_id>/<version>/catalog.geojson.
Full source manifests and registry proposals accompany each catalog. The live tests
used a two-catalog validation registry; configs/spatial_dataset_providers.json in
the production branch was not activated or silently rewritten. Its legacy PRVI
entry is still unbound. A consumer must materialize and validate the archived
catalogs and explicitly apply the reviewed proposal before using them in deployment.

## Real AOI results

AOIs below are deliberately chosen test rectangles, not user-supplied polygons or
authoritative administrative boundaries. Coordinates are west,south,east,north.
All file decisions are exact intersections against the published STAC footprints;
those footprints are not certified valid-pixel/observation masks.

| Test AOI | m9101 files | m8571 files | Total retained | Excluded | Unresolved | Planning |
|---|---:|---:|---:|---:|---:|---|
| coastal_test: -66.13,18.44,-66.07,18.48 | 19 | 34 | 53 | 7169 | 0 | PASS |
| inland_test: -66.60,18.16,-66.57,18.19 | 9 | 0 | 9 | 7213 | 0 | PASS |
| offshore_negative: -66.00,19.00,-65.99,19.01 | 0 | 0 | 0 | 7222 | 0 | BLOCKED |

The coastal AOI recommends both sources independently. Inland recommends m9101 only.
The offshore case yields NO_MATCH_IN_SNAPSHOT, never empty acquisition READY.
Complete responses retain all 7,222 candidate rows; selected-file manifests expose
exact dataset/row/asset identities, URLs and spatial relations. Cache is NOT_CHECKED,
Fetch is false, usable-data coverage is UNKNOWN and overall certification is OPEN.

## Executed code and rendering gates

- 138 Python tests passed, zero failures/skips: retained 111 plus 27 new profile,
  conflicting-evidence, URI-identity and derivative-version tests. The same suite
  passed in local and isolated network runtimes; this is not 276 distinct tests.
- Full locked frontend install succeeded. All 124 existing frontend tests across
  16 test files passed. The 11 AOI tests are a subset, not extra tests to double-count.
- Full frontend typecheck, ESLint and production Vite build passed after narrow fixes.
  A pre-existing Array.at/lib mismatch and six lint violations were corrected without
  disabling rules or weakening validation. The build reports large-chunk warnings.
- Three additional live-catalog React/jsdom tests passed using the actual frozen
  coastal/inland/offshore responses. Both-source selection resolves 53 coastal files;
  pagination visits every file exactly once. The first test assumed an unpaginated
  table and failed at 50 rows; correcting the test to traverse pages required no
  source changes or catalog redownload. Both attempts are preserved.
- Browser-native MapLibre/WebGL drawing and iPhone portrait/landscape verification
  were NOT completed. jsdom is not a browser screenshot or device certificate.
- Full production backend startup/deployment and current-head GitHub hosted checks
  are not certified by these isolated tests. Existing acquisition remains disabled.

## Frozen archive

URL:
https://spiderweb-pr.floot.app/_cdn/static/764df81c-9cf7-417a-9745-463acf36827d-spiderweb-noaa-live-catalogs-20260913.zip

ZIP bytes: 8699855
ZIP SHA-256: 7e78c619d9371bc8a4e85f88679c968be3ce8e53a4b11d88176e1caae8b65ead

The archive contains 60 payload members plus ARCHIVE_MANIFEST.json. Each payload has
PATH + UNCOMPRESSED_SIZE + SHA-256; payload total is 237539720 bytes. Manifest SHA-256:
75c90a2f2ce8c9e9e0068192bf851a5dcfe267aa174086d378a0ba7bb253cb34

Upload and complete read-back both returned HTTP 200. Read-back size and SHA-256
matched. Storage receipt UTC: 2026-09-13T17:21:30.716Z. This freezes source bytes,
normalized catalogs, full candidate responses, selected-file lists, collisions,
transformation sources, runtime manifests and test logs. No fonts, dependency trees,
raster bytes, private user AOIs or project secrets are included.

## Remaining scope

Production catalog installation/activation, browser-native drawing and mobile
verification, all-provider dataset enumeration, gis.pr.gov/TNM/vector-service
adapters and equivalence adjudication remain OPEN. Asset downloads, validated cache,
format checks and actual valid-observation coverage remain a separate later gate.
The two-catalog success must not be reported as 100% Puerto Rico source completeness
or end-to-end POLYGON -> FILES acquisition certification. Keep PR #357 draft.
