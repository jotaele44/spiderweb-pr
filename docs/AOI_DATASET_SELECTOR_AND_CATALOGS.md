# AOI dataset selector and catalog bootstrap — bounded continuation

PR #357; branch feat/aoi-acquisition-workbench. Continuation of
27945a6f05cb7721c36848071164ad0189b79cca. Status: DRAFT / OPEN.

## Implemented user path

Draw/import the AOI, set optional filters, then run Dry Run. The existing map
workbench now calls POST /spatial/aoi/recommendations and mounts a searchable,
expandable dataset multiselect. Only backend-recommended datasets appear in the
ordinary choices. No dataset is preselected or assigned preferred-source status.
Other/no-match/filtered/processing-only/unresolved decisions remain inspectable.
A known match with unresolved residual rows carries an incomplete-file warning.

Selecting one or several datasets resolves their applicable_file_row_ids into
the original full plan.assets rows. The selected-file table shows the dataset,
asset ID, exact row ID, AOI relation, external source URL and validation state.
The map displays those selected source footprints; an explicit audit toggle
shows every catalog footprint instead. No new client-side spatial selection or
source identity authority was introduced.

AOI/filter/buffer edits, imports, drawing and clearing invalidate the response
and selection. The prior abort/revision gates and AOI-response binding remain.
Export preserves the complete server response inside a separate user-selection
wrapper. Selection is not acquisition authorization and the wrapper is not a
signed certificate. Application Fetch remains disabled.

## Frontend rejection gates

The TypeScript recommendations parser validates the nested v1.1 plan, catalog
and dataset census, complete row membership, exact referenced file lists,
recommendation states, unresolved/processing-only lists, transfer estimates,
AOI/registry bindings and closed arithmetic. It rejects stale/nonrecommended
selection IDs, missing or cross-dataset rows, unexpected acquisition/coverage
claims and fabricated dataset equivalence. Server-generated hash identifiers are
validated structurally; this is not browser cryptographic verification of the
whole response or a source-authenticity signature.

## Two published catalog locators, not an all-Puerto-Rico inventory

configs/aoi_catalog_sources.json registers:

- NOAA_OCM_m9101: 2018 USGS Lidar DEM: Post Hurricane Maria - Puerto Rico.
  Original producer: USGS; publication: NOAA Digital Coast.
- NOAA_OCM_m8571: 2018 USACE FEMA Topobathy Lidar DEM: Main Island, Culebra,
  and Vieques, Puerto Rico. Original producers named by publication: USACE/FEMA;
  publication: NOAA Digital Coast.

Official discovery pages:
https://coast.noaa.gov/htdata/raster2/elevation/USGS_PostMaria_PuertoRico_DEM_2018_9101/
https://chs.coast.noaa.gov/htdata/raster2/elevation/USACE_PR_Topobathy_DEM_2018_8571/

These pages expose tile indexes, source URL lists and STAC catalog links. The
publisher's raw collection IDs retain the word 'imagery'; no name correction or
inferred identity with the existing PRVI_1m_DEM_2018 entry was made. Different
product/producer labels alone do not certify source independence or equivalence.

The two new provider declarations remain DISCOVERED_UNBOUND with null catalog
path, hash and record count. Together with the preserved legacy PRVI declaration,
the configured registry has three dataset entries, all unresolved without valid
catalog snapshots. Declarations are not loaded datasets. No source file count or
spatial availability is fabricated for them.

## Restartable metadata-only bootstrap

From an environment with the repository, GIS dependencies and network access:

    python -m tools.aoi_catalog_snapshot --source NOAA_OCM_m9101 \
      --work-dir /absolute/path/to/snapshots/m9101-attempt-1
    python -m tools.aoi_catalog_snapshot --source NOAA_OCM_m8571 \
      --work-dir /absolute/path/to/snapshots/m8571-attempt-1

The command acquires metadata only, never DEM/point-cloud files. Reuse the same
work directory after a downstream failure. A new snapshot requires a different
work directory. Corrupt/incomplete old inputs fail closed rather than being
silently replaced with newer bytes.

Successful conversion writes immutable raw Collection, ItemCollection and URL
list bytes; retrieval receipts; a source manifest; normalized file-footprint
GeoJSON; and a registry proposal. It does not activate that proposal. Review the
manifest and a real AOI test before updating the matching provider declaration.
An unsupported actual source schema remains BLOCKED until narrowly adapted and
regression-tested; the importer is not advertised as universal STAC support.

## Catalog gates

Collection stable ID, item collection IDs and exact self/item links must bind.
Every asset is classified as data or an explicitly recognized auxiliary role.
Current scope requires exactly one data asset per Item; multiple data assets,
asset-specific geometries, unconsumed pagination/hierarchy, unknown roles and
unexpected CRS members require review rather than silent fallback.

The exact collection-item link set and the independently published file URL list
must close against the selected ItemCollection records and data URLs. For each
comparison, preserve INTERSECTION, A_ONLY, B_ONLY, UNION and SYMMETRIC_DIFFERENCE.
Repeated IDs/URLs, missing members or extra members fail closed. Equal counts or
similar basenames do not establish identity.

Source requests are restricted to configured HTTPS dataset prefixes, without
credentials, redirects, query strings or traversal. Byte/row bounds, response
length checks, SHA-256, timestamp/header receipts and write-once publication are
required. Existing validated raw bytes are reused without network requests.

Published Item geometry is preserved as a source footprint, not a valid-data
mask. Null geometry is never substituted with a bbox. STAC datetime is not
promoted into lidar acquisition date, and missing resolution remains unknown.
Raw source bytes and IDs remain available independently of the derived catalog.

## Executed verification

Local final run: 79 Python tests PASS, zero failures/skips (36 existing relevance
tests plus 43 new catalog-adapter tests). They exercise exact dataset/file
recommendations, holes/multipart gaps/touch-only cases, catalog and URL closure,
unsupported source variations, raw preservation, cache/no-network reuse,
write-once conflict handling, registry proposals and frozen synthetic catalog to
AOI recommendation integration. All source fixtures use TEST_ONLY/example.invalid.

Strict compilation of the actual TypeScript recommendation/plan contracts passed.
32 Node runtime tests against the compiled production parser and a Python-produced
synthetic response passed, zero failures/skips. Four React/Vitest selector tests
were added but not executed locally. TSX transpilation reported no syntax errors;
that is not full application typecheck/build/render verification.

The dedicated AOI workflow now includes backend catalog tests, frontend install,
full frontend typecheck, AOI unit/render tests, the cross-language parser test and
production build. Workflow configuration is not evidence those hosted jobs passed.

## Live acquisition attempt and remaining boundaries

The m9101 metadata-bootstrap attempt exited 1 with Temporary failure in name
resolution. No live catalog snapshot was completed or activated and no raster
asset was fetched. Browser-parsed source text was not substituted for source raw
bytes or a source SHA-256. This is an environment failure, not public-source
exhaustion and not evidence that the official catalog is empty/unavailable.

Still OPEN: live schema/byte ingestion and catalog activation; full production
application startup/typecheck/build; rendered MapLibre and iPhone verification;
all-provider inventory and equivalence adjudication; additional vector/WFS/TNM
adapters; actual asset cache/acquisition/hash/format validation; usable coverage;
and full POLYGON -> FILES certification. Existing original planner/relevance code
is reused unchanged; no inherited PASS from its older tests was added to the
79-test denominator above. PR remains draft, unmerged and undeployed.
