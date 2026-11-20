# USGS documentary reference export

`federation/usgs_native_reference.py` owns the source-native USGS adapter.
`scripts/export_usgs_native.py` uses the existing canonical package writer in
`scripts/federation_export.py`. The adapter reads checksum-verified inputs
supplied by the Hub; it does not acquire mutable sources.

The frozen regression scope is three NSHM2025 source assets: 51 points, six
MultiPolygons and 35 MultiLineStrings. Export conservation is 3 sources and 92
snapshot observations. Entire native features and collection metadata including
CRS remain in attributes. Source primary keys are typed and scoped to the asset
and raw payload hash. No names or coordinate proximity establish identity.

This is a **test-mode documentary reference package**. `observed_at` describes
source retrieval, never a geological event. Confidence 0 means domain confidence
is unassessed; the separate checksum proof describes byte integrity. The export
contains no canonical locations, representative points, new event claims,
geometry transformations or jurisdiction assignments. It is excluded from live
aggregation. PR coverage, native geometry interpretation, usage, lineage,
consumer fitness and scientific semantics remain OPEN. Production mode fails
before writing anything. Existing producer production exports are unchanged.

From this repository root, with the normal `prii-export-utils` dependency:

```sh
python -m pytest -q tests/test_usgs_native_reference.py tests/test_federation_export.py
python scripts/export_usgs_native.py --input-manifest tests/fixtures/usgs_native/input.json --source-root . --out /absolute/path/new-empty-package
```

For the real Hub staging input use its `data/usgs/producer_inputs/spiderweb-native.v1.json`
as `--input-manifest` and its repository root as `--source-root`. The produced
package includes `TERMINAL_READY.txt`. Validate with the Hub's canonical package
validator and the independent USGS export validator on its companion PR branch. Schema PASS
is explicitly separate from scientific or production readiness.

Regression gates include duplicate IDs and primary keys, missing/foreign source
identity, typed integer/string keys, checksum disagreement, path escape,
expanded-size limits, duplicate JSON fields, non-finite values, count drift,
naive timestamps, production refusal and deterministic replay. A nonempty output
directory fails closed so previous packages cannot be partially overwritten.

## Frozen cross-format review

`scripts/review_usgs_sources.py` uses the producer-owned
`federation/usgs_source_review.py` to compare preserved GeoJSON with three paired
CSVs and the FGDC metadata. Install the existing Shapely dependency (>=2.1,<3).
Run `python -m pytest -q tests/test_usgs_source_review.py`.
Run `python scripts/review_usgs_sources.py --input tests/fixtures/usgs_source_review/input.json --source-root . --out /absolute/path/new-review.json`.
Expected exit: **2**, scientific staging BLOCKED. Existing output paths are refused.
The diagnostic is a maintenance CLI, not an added canonical export command.

All 3 native geometries pass format checks, but all 3 cross-format comparisons
fail. Preserve EGQ5/EQG5, 15 raw numeric CSV/GeoJSON tuple differences, shortened
text, blank/N/A/null distinctions and the FS6 HIS/Offshore conflict. CSV CRS/axis
semantics remain unverified; do not label raw numeric deltas as physical distances.
Two layers exceed the publisher's PRVI extent; that extent is not PR jurisdiction.
Literal FGDC access/use fields `none` close recording only. The migration note's
no-data-change wording is a source claim, not verified byte lineage.
No aliases, geometry repair, production export or activation are authorized by
this review. CI passes only when the implementation preserves these conflicts
and refuses scientific staging; it does not certify the dataset.


## KML corroboration (2026-10-19)

The maintenance command `scripts/review_usgs_kml.py` compares all three frozen
KMLs with the previously reviewed CSV and GeoJSON. No successful bytes were
reacquired. Run `python -m pytest -q tests/test_usgs_kml_review.py` and
`python scripts/review_usgs_kml.py --input tests/fixtures/usgs_kml_review/input.json --source-root . --out /absolute/path/new-kml-review.json`.
Expected exit 2: AUDIT_ONLY, scientific staging/certification BLOCKED.

Stable-key intersections with GeoJSON are 51/6/35; symmetric differences are 0.
CSV-to-KML preserves EGQ5/EQG5 (intersection 50, union 52, symmetric difference 2)
and 15 raw numeric coordinate conflicts. KML also records FS6 as Offshore, but
two agreeing source formats do not establish authority over the CSV HIS value.
All 92 geometry comparisons fall within a declared 1e-10 raw numeric tolerance
(maximum 5e-14); only 36 are exact comparison objects and topologically equal.
No snapping, topology repair, coordinate rounding or canonical export is done.
The comparison retains native geometry tags, dimensions and coordinate text.
71 numeric property serialization differences and 43 missing-versus-null fields
remain explicit. The polygons KML declares an internal v0 schema while its
filename declares v1; this is unresolved version-label evidence, not proof of
an older or newer authoritative release. The supporting README records WGS84 and scientific unit definitions.
Its X/Y axis definitions contradict the values and geometry; actual unit-value
validation remains unresolved.

Regressions reject duplicate IDs/fields, wrong schema URLs, unknown geometry,
network links, nonfinite coordinates, DTD/entity declarations and unclosed rings.
Rehashed changed geometry is retained as conflicting evidence; excessive
tolerances cannot hide it. Whole stable-key rows remain separate.

The release also has four byte-passing supporting documents. Their 44 field
definitions and full raw changelog rows are retained. The publisher directs
users to CSV for complete Obsern text and allows sites outside the hazard area;
this does not define a PR jurisdiction mask or prove the metadata bbox's role.
The README labels X as latitude and Y as longitude, conflicting with the
negative-longitude X values and GeoJSON/KML tuples. No axis swap is performed.
RecurUn in the README versus RecurUnc in data remains an unresolved schema label.
The fault changelog retains 36 rows: 35 keyed matches and one blank-key Bowin
row, which is neither dropped nor joined by name. The polygons changelog has
6 keyed matches. FS6 Offshore is corroborated by the fault changelog. The 14-file legacy top-level review denominator is independently checked by the Hub; this
excludes external links/services and does not claim current-version completeness.

The Hub's recursive metadata scan additionally found 16 shapefile components
in facets and 30 distribution-file references for this release. These 46 nested
references were outside the legacy top-level inventory. They are not certified
unique assets or verified payloads. Across the catalog, 850 facet references,
3,136 distribution-file references and 702 non-array files fields remain separate
from the original 2,286 top-level references. Full file/payload closure is OPEN.
The original counts and evidence remain preserved, not silently replaced.
