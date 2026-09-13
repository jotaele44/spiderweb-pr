# Dataset -> file relevance v1.0

Status: DRAFT / OPEN. This is a bounded backend implementation, not a complete
Puerto Rico dataset inventory or POLYGON -> FILES certification.

## Requirement

The user supplies one Polygon/MultiPolygon. The backend identifies applicable
datasets across all configured source manifestations and the exact indexed
files/tiles within each, preserving the alternatives for user comparison.
A flat provider menu, a country-sized bbox, a keyword, or a shared product name
is not proof that a dataset or a file applies to that AOI.

## Endpoint

POST /spatial/aoi/recommendations accepts the same AOI, raw import text,
product/provider/date/resolution filters and separate processing buffer as the
existing POST /spatial/aoi/plan endpoint. It accepts no caller bbox, catalog path,
source registry, arbitrary fetch URL or precomputed plan. Both endpoints remain
read-only. The existing v1.1 plan response is unchanged.

The new endpoint freezes a response containing the unchanged plan, one summary
per registered dataset, and lists of recommended/unresolved/processing-only
dataset IDs. The plan contains the full original asset rows, including source
URLs, original footprints, exact intersections, asset identities and exclusions.
Each summary's applicable_file_row_ids references those rows without synthesizing
or merging their attributes. all_row_ids preserves the complete snapshot census.

## Deterministic decision semantics

- RECOMMENDED: at least one source-bound, filter-retained file footprint has
  positive-area intersection with the original AOI.
- RELEVANT_UNRESOLVED: known spatial overlap exists, but identity or requested
  metadata/filter evidence prevents a usable file recommendation.
- FILTERED_OUT: overlap exists but the requested product/date/provider/resolution
  filters explicitly exclude the known matching files. This is not geographic
  absence.
- PROCESSING_ONLY: known applicable files overlap only the processing extension.
  They are not promoted into original-AOI recommendations.
- NO_MATCH_IN_SNAPSHOT: the examined snapshot has no positive-area AOI match,
  with no unknown source geometry. This says nothing about other snapshots.
- UNRESOLVED: catalog/geometry evidence cannot establish applicability.

A dataset with one verified match plus unknown rows can be recommended for its
known match while file_resolution_state remains UNRESOLVED. The unknown rows and
an incomplete-list warning must remain visible. No complete-file-list claim is
permitted in that case. Dataset and file denominators are separately conserved.
A complete but empty snapshot can yield NO_MATCH_IN_SNAPSHOT; it never yields
acquisition READY. Provider/catalog failures are never an empty-success result.

## Dropdown integration contract (NOT mounted by this patch)

After every AOI/filter/buffer edit, invalidate the previous response. Submit the
AOI to the new endpoint; reject a response for a stale revision or another AOI.
Use recommended_dataset_ids to populate the ordinary multi-select dropdown.
Show provider + dataset label/version + applicable file count, and an explicit
incomplete-list warning where file_resolution_state is not PASS. Keep unknown,
filtered-out, no-match and processing-only datasets in separate inspectable views.
Do not hide their counts or recalculate geographic decisions in the browser.

When a dataset is selected, resolve its applicable_file_row_ids against plan.assets
by exact row ID. Display the file's asset ID, source URL, footprint/intersection,
spatial relation and validation status. Keep source manifestations separate.
A dataset-class grouping is a convenience, not certified source equivalence.
The menu does not choose a preferred producer or collapse overlapping sources.

This patch does not enable Fetch, make a browser-ready deployment, or mount the
new dropdown. Those remain explicit integration work, not inherited PASS.

## Scope and evidence

The adapter currently evaluates hash-pinned GeoJSON file-footprint catalogs
registered on the server, with explicit record counts. It enumerates all rows
within that bounded input rather than relying on a bbox-only query. Other source
protocols (STAC, TNM, ArcGIS, WFS, vector-service subsets, archive-member indexes)
need their own adapters and provenance gates. A vector service with relevant
features does not automatically identify a pre-existing source tile or file.

The production registry observed at f09651ec8ba33dad7e14832e87826d9ca4d11781
contains PRVI_1m_DEM_2018 with catalog_path null and VRT format. It is UNRESOLVED,
not a verified recommended dataset. No all-provider/all-PR inventory was built.
No equivalence pairs were adjudicated. Global completeness remains UNRESOLVED.

A recommendation identifies a source footprint, not a valid-observation mask.
Download completion, hashing, format validation, actual coverage, and overall
certification remain separate. The response hash detects changed exported bytes;
it is not a signature or upstream source-authenticity proof.

## Executed verification

36 local Python tests cover two-level dataset/file selection, holes, multipart
gaps, partial overlap, touch-only contact, unknown/empty catalogs, null geometries,
filters, processing-only buffers, separate same-named source files, duplicate URL
residue, raw preservation, hash binding, stale registry rejection, complete
row/dataset arithmetic, malicious request-field rejection, both HTTP routes, and
absence of a Fetch endpoint. Fixtures use TEST_ONLY and example.invalid only.

The production planner was reconstructed locally and matched its Git blob
5cf25aebce8562cfde73ed7bfb0502ca3860456a before tests. It was not changed.
Only a FastAPI router TestClient was exercised, not full application startup,
hosted CI, MapLibre rendering, iPhone interaction or live catalogs.

Reproduce from the repository root with server/geo/test dependencies installed:

    python -m pytest tests/test_aoi_relevance.py -q
