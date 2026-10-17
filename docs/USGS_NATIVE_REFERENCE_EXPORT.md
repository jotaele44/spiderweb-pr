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
