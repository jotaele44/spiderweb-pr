# AOI mixed URL inventory — bounded continuation

PR #357; parent `bef427f3887584cba7e660636f53d820b309261b`.
Status: DRAFT / OPEN. No merge, activation, deployment or source-data acquisition.

## Source observation and corrected assumption

The published NOAA m9101 URL list contains TIFF assets, STAC item JSON,
Collection/ItemCollection/catalog JSON, the URL list itself, additional inventory,
XML/HTML metadata, a zipped tile index, and a VRT. The earlier importer required
every nonblank URL to end in .tif/.tiff. That would reject this mixed list even
with successful network access. The failure was safe, but prevented ingestion.

Official observation source:
https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/USGS_PostMaria_PuertoRico_DEM_2018_9101/urllist9101.txt

Official collection:
https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/USGS_PostMaria_PuertoRico_DEM_2018_9101/stac/collection.json

The browser's parsed excerpts were used to identify this schema variation and
bind eight exact auxiliary URLs in the m9101 source configuration. They were NOT
used as raw downloaded source bytes, catalog hashes, a complete dataset census,
or an activated provider catalog. Original `PeurtoRico` spellings remain intact.
The m8571 configuration is not assigned m9101's auxiliary inventory by analogy.

## Implemented boundary

`aoi_url_inventory.py` classifies each original URL-list line as DATA,
ITEM_METADATA, CATALOG_METADATA, DECLARED_AUXILIARY, BLANK or UNRESOLVED.
Original strings, line numbers, line endings and UTF-8 BOM presence are retained.
No suffix-only removal of unknown XML/JSON/ZIP files is permitted.

DATA requires exact membership in the independent STAC data-asset URL set.
ITEM_METADATA requires an exact linked item-self URL. CATALOG_METADATA requires
an exact configured structural URL. DECLARED_AUXILIARY requires an exact URL,
explicit role and evidence reference in server-owned configuration. These links
bind publication entries; they do not establish byte identity or independent
measurement provenance. Data-looking files cannot be declared auxiliary to hide
a missing STAC data member.

All unknown, unsafe, duplicated or ambiguously classified rows remain in a
BLOCKED audit. A suffix can discover an extra data candidate for the set-difference
report; it cannot promote that candidate into the acquisition plan. The DATA URL
comparison records INTERSECTION, A_ONLY, B_ONLY, UNION and SYMMETRIC_DIFFERENCE,
plus multiset/duplicate gates. Metadata does not inflate the data-file count.
Legacy data-only manifests remain supported. Item-metadata presence in a bulk
URL list is optional; the independent Collection-to-ItemCollection gate still
requires complete item-link closure.

`convert_snapshot` now includes this complete audit in its frozen source manifest.
When this stage fails, `freeze_catalog` preserves a hash-bound failure report
beside the frozen inputs. Repeating the same failed vector reuses the report;
no incomplete registry proposal or valid catalog is emitted. Existing validated
raw inputs remain reusable; the code does not redownload them after conversion
failure. Source assets remain untouched and Fetch stays disabled.

## Executed verification

111 Python tests passed with zero failures/skips: 79 previously retained
relevance/catalog tests plus 32 new URL-inventory regressions. New cases include
mixed manifests, exact roles, unknown metadata, duplicates, safe URL boundaries,
BOM/CRLF preservation, missing/extra data, false auxiliary declarations, bounded
freeze-failure receipts, and metadata-to-exact-AOI recommendation integration.
All executable catalog fixtures are synthetic TEST_ONLY/example.invalid inputs.

Strict compilation of the unchanged TypeScript contracts passed. Their 32 Node
runtime tests passed. The first Node command used an incorrect relative module
path; it was rerun with the existing compiled artifact's absolute path. No source
redownload or code rewrite was required for that invocation error.

Both real metadata-bootstrap attempts (m9101 and m8571) exited 1 because runtime
DNS resolution failed. Direct file-download transport also failed. npm registry
connectivity failed DNS resolution, and the required React/Vitest/MapLibre
application dependencies were not installed. No full frontend typecheck/build,
React render, MapLibre or iPhone runtime verification is claimed.

The configured provider registry remains unchanged: three declared, unresolved
entries; no loaded live file-footprint snapshots. No real AOI file recommendation,
all-source inventory, source-equivalence adjudication, valid-observation coverage
or end-to-end POLYGON -> FILES certificate is established by this continuation.

## Remaining exact gate

Acquire and preserve raw Collection, ItemCollection and mixed URL-list bytes;
close all schema/identity/URL inventory gates against those bytes; activate only
a reviewed proposal; then run a real polygon through the dataset selector and
rendered desktop/mobile workflow. No fabricated catalog counts or automatic
provider preference may substitute for those steps.
